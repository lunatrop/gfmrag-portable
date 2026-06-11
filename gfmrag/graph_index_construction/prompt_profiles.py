"""Per-dataset prompt profiles for NER + OpenIE extraction.

The extraction prompts are corpus-dependent (a register of company filings
needs identifier-aware prompts; news text needs different guardrails), so
they are data, not code: a ``prompts.yaml`` placed in a dataset's ``raw/``
directory — next to ``documents.json`` — overrides the packaged defaults for
that dataset only. Resolution order:

    <data_root>/<data_name>/raw/prompts.yaml   (applied by KGConstructor)
    > prompts_file passed to LLMOPENIEModel    (hydra-overridable)
    > packaged defaults                        (openie_extraction_instructions)

Profile schema::

    ner_instruction: |        # system message for the NER call
    openie_instruction: |     # system message for the OpenIE call
    one_shot:
      passage: |              # example document
      entities: [...]         # expected NER output (list of strings)
      triples:                # expected OpenIE output (list of [s, r, o])
        - [subject, relation, object]
"""

import json
import logging

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from gfmrag.graph_index_construction import openie_extraction_instructions as defaults

logger = logging.getLogger(__name__)


def default_profile() -> dict:
    """The packaged (upstream HippoRAG-derived) prompts."""
    return {
        "ner_prompts": defaults.ner_prompts,
        "openie_prompts": defaults.openie_post_ner_prompts,
    }


def load_prompt_profile(path: str) -> dict:
    """Build the two ChatPromptTemplates from a prompts.yaml profile.

    Mirrors the message structure of the packaged defaults exactly:
    system instruction + one-shot (human, ai) + templated user turn.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    passage = data["one_shot"]["passage"].strip()
    entities_json = json.dumps(
        {"named_entities": data["one_shot"]["entities"]}, ensure_ascii=False
    )
    triples_json = json.dumps(
        {"triples": [list(t) for t in data["one_shot"]["triples"]]},
        ensure_ascii=False,
        indent=1,
    )

    ner_prompts = ChatPromptTemplate.from_messages(
        [
            SystemMessage(data["ner_instruction"]),
            HumanMessage(f"Paragraph:\n```\n{passage}\n```\n"),
            AIMessage(entities_json),
            HumanMessagePromptTemplate.from_template(defaults.ner_user_input),
        ]
    )

    openie_one_shot_input = defaults.openie_post_ner_frame.replace(
        "{passage}", passage
    ).replace("{named_entity_json}", entities_json)
    openie_prompts = ChatPromptTemplate.from_messages(
        [
            SystemMessage(data["openie_instruction"]),
            HumanMessage(openie_one_shot_input),
            AIMessage(triples_json),
            HumanMessagePromptTemplate.from_template(defaults.openie_post_ner_frame),
        ]
    )

    logger.info(f"Loaded prompt profile from {path}")
    return {"ner_prompts": ner_prompts, "openie_prompts": openie_prompts}
