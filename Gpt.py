import json
from settings import DEFAULT_GPT_MODEL
from openai import OpenAI
from tiktoken import encoding_for_model
from random import randint


class Gpt:

    def __init__(
            self,
            api_key: str,
            system_prompt: str,
            model_name: str = DEFAULT_GPT_MODEL,
            max_tokens=None
    ):
        super().__init__()
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)
        self.context = []

    def _get_system_prompt_message(self):
        """
        Returns the system prompt message containing the content from the system prompt file,
        in the format that is expected by the OpenAI-API.
        :return: The system prompt message
        """
        return {"role": "system", "content": self.system_prompt}

    def _add_prompt_to_context(self, role, prompt, function_call=None):
        new_message = {"role": role, "content": prompt}
        if function_call:
            new_message["function_call"] = function_call

        self.context.append(new_message)

    def _get_completion(self):
        """
        Gets the completion of the model in the current state
        :return: The ChatCompletionMessage object from the current state completion
        """
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[self._get_system_prompt_message()] + self.context,
            seed=randint(1, 64000)
        )
        return completion

    def answer_prompt(self, prompt):
        """
        Answer the given prompt or iterate on given context if prompt is None
        :param prompt: The prompt
        :return: The answer to the prompt or existing content
        """
        # Add the prompt to the context if it is not null, else just iterate on existing context
        if prompt:
            self._add_prompt_to_context("user", prompt)
        # Retrieve completion based on context
        completion = self._get_completion()
        answer = completion.choices[0].message
        self._add_prompt_to_context("assistant", answer)
        return answer

    def count_tokens(self):
        """Returns the number of tokens in the context window."""
        encoding = encoding_for_model(self.model_name)
        num_tokens = 0
        for msg in self.context:
            num_tokens += len(encoding.encode(str(msg)))
        return num_tokens



if __name__ == '__main__':
    prompt = ("Your job is to infer, from an input table of contents, what sections are mapped to what pages. You should only do this for sections that have subsections and where these subsections start with (L1) or (L2) and can ignore sections without. You should return a list of tuples (a, b), where a is the name of the parent section. If a section has multiple sub-sections, you should always return for the innermost. B is a tuple (x,y) where x and y are the starting and ending page for the section (starting for next section -any) "
              "For instance, for the table of contents: "
              "1 Above Lock  ................................ ................................ ................................ ........................ 34 "
              "1.1 (L1) Ensure 'Allow Cortana Above Lock' is set to 'Block' (Automated)  ...............................  35 "
              "2 Account Management  ................................ ................................ ................................ ........ 37 "
              "3 Accounts  ................................ ................................ ................................ ............................ 37  "
              "Page 3 4 Administrative Templates  ................................ ................................ ................................ .37 "
              "4.1 Control Panel  ................................ ................................ ................................ ................................ .. 37 "
              "4.1.1 Add or Remove Programs  ................................ ................................ ................................ ....... 37 "
              "4.1.2 Display  ................................ ................................ ................................ ................................ ....... 37 "
              "4.1.3 Personalization  ................................ ................................ ................................ .........................  37 "
              "4.1.3.1 (L1) Ensure 'Prevent enabling lock screen camera' is set to 'Enabled' (Automated)  ... 38 "
              "4.1.3.2 (L1) Ensure 'Prevent enabling lock screen slide show' is set to 'Enabled' (Automated)"
              "................................ ................................ ................................ ................................ ..................  40 "
              "4.1.4 Printers  ................................ ................................ ................................ ................................ ...... 42 "
              "4.1.5 Programs  ................................ ................................ ................................ ................................ ... 42 "
              "4.1.6 Regional and Language Options  ................................ ................................ ............................  42 "
              "4.1.7 User Account  ................................ ................................ ................................ ............................  42 "
              "4.2 Desktop  ................................ ................................ ................................ ................................ ...........  42 "
              "4.3 LAPS (legacy)  ................................ ................................ ................................ ................................ . 42 "
              "4.4 MS Security Guide  ................................ ................................ ................................ .........................  42 "
              "4.4.1 (L1) Ensure 'Apply UAC restrictions to local accounts on network logons' is set to 'Enabled' (Automated)  ................................ ................................ ................................ ...............  43"
              "\n You would return [('1. Above Lock', (34, 37)), ('4.1.3 Personalization', (37, 42)), ('4.4 MS Security Guide', (42, 43))]")
    gpt = Gpt(prompt, DEFAULT_GPT_MODEL)
