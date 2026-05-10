"""Azure AI Foundry binding.

A single Azure OpenAI route shape on the Cognitive Services account serves
all 10 dev-account candidates — OpenAI-family AND serverless (Llama,
Mistral, Phi, Kimi). Confirmed in MLI-166. The concrete binding lives in
sibling module `binding`; importing it triggers self-registration under
the name `'azure_foundry'`.
"""
