from strands import Agent
from strands.models import BedrockModel
import boto3

# define model to use
model = BedrockModel(
    model_id="us.amazon.nova-lite-v1:0",
    region_name="us-east-1",
)

# system prompt: currently commented out
'''
SYSTEM_PROMPT = """
You are taking on the persona of Dana Reyes, a Emergency Operations Center (EOC) public-information officer.
Text residents official bulletins.
When responding to residents, only respond with validated official data.
Search for emerging rumors, verify them with Bedrock, and draft a clarification for a human to review and approve.
After sending clarifications, track whether the rumor is dying down or not.
"""
'''

# pass model and system prompt to agent
agent = Agent(model=model)
              # system_prompt=SYSTEM_PROMPT)

# get agent output for this response
agent("Is this Converse API call working?")



