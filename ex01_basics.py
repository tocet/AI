#https://lmstudio.ai/docs/python
import lmstudio as lms

model = lms.llm("pllum-12b-chat")
result = model.respond("Przedstaw się. Podaj nazwę modelu.")

print(result)
