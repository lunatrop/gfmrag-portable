from langchain_ollama import OllamaLLM

# Initialize the LLM
llm = OllamaLLM(model="gemma:2b")

# Invoke the model
result = llm.invoke("What is the capital of France?")
print(result)