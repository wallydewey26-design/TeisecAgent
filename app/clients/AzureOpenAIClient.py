import json
from openai import AzureOpenAI,BadRequestError,APIConnectionError
from colorama import Fore
from app.Prompts import TeisecPrompts
class AzureOpenAIClient():
    def __init__(self,api_key,azure_endpoint,model_name):
        self.model_name=model_name
        self.client=AzureOpenAI(
        azure_endpoint = azure_endpoint, 
        api_key=api_key,  
        api_version="2024-05-01-preview"
        )
        # Create log directory if it doesn't exist
        os.makedirs('log', exist_ok=True)
    
    def runPrompt(self,prompt,session={},scope='core'):
        if ("messages" in session and len(session["messages"])>0 and session["messages"][0]['role']=='system'):
            #session already contains System message
            message_object=[]
        else:
            #session without System Message. Using Default
            message_object = [{"role":"system","content":[{"type":"text","text":TeisecPrompts["Core.Main.System"]}]}]
        if session is not None and "messages" in session:
            message_object.extend(session["messages"])
        message_object.append({"role":"user","content":[{"type":"text","text":prompt}]})
        result=''
        status='success'
        session_tokens=''
        
        # Only log in debug mode to reduce I/O
        debug_mode = os.getenv('DEBUG_MODE', 'False') == 'True'
        if debug_mode:
            try:
                with open('log/'+scope+'.log', 'a', encoding='utf-8') as f:  
                    f.write("\nSESSION:\n")
                    f.write(json.dumps(message_object, ensure_ascii=False, indent=4))
                    f.write('\nPROMPT:\n')
                    f.write(prompt)
            except Exception:
                pass  # Silently ignore logging errors
        
        try:
            completion = self.client.chat.completions.create(
            model=self.model_name,#Deployment Name
            messages = message_object,
            temperature=0.7,
            max_tokens=4000,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
            )
            result=completion.choices[0].message.content
            #prompt_total_tokens=str(completion.usage.total_tokens)
            #prompt_input_tokens=str(completion.usage.total_tokens)

        except BadRequestError as e:  
            status='error'
            result=e.code+' - '+e.message
        except APIConnectionError as e:
            status='error'
            result=e.message
            print (e)
        session_tokens_object=[]
        usage=completion.usage
        tokes_object={"prompt_tokens":usage.prompt_tokens,"completion_tokens":usage.completion_tokens,"total_tokens":usage.total_tokens}        
        session_tokens_object.append({"scope":scope,"tokens":tokes_object})
        result_object={"status":status,"result":result,"session_tokens":session_tokens_object}
        
        # Only log in debug mode to reduce I/O
        if debug_mode:
            try:
                with open('log/'+scope+'.log', 'a', encoding='utf-8') as f:  
                    f.write("\nRESULT\n")
                    f.write(result)
            except Exception:
                pass  # Silently ignore logging errors
        
        return result_object