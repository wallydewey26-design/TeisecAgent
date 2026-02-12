import os  
from azure.identity import InteractiveBrowserCredential, ClientSecretCredential, DefaultAzureCredential  
from app.clients.SentinelClient import SentinelClient  
from app.clients.AzureOpenAIClient import AzureOpenAIClient  
from app.clients.GraphAPIClient import GraphAPIClient 
from colorama import Fore  
from app.HelperFunctions import *  
from app.Prompts import TeisecPrompts
import json 
import time  
import concurrent
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from functools import partial
import traceback
import uuid
import importlib
class TeisecAgent:  
    def __init__(self, auth_type):  
        self.client_list = {}  
        self.plugin_list = {} 
        self.plugin_capabilities={}
        self.sessions ={}
        self.context_window_size = int(os.getenv('ASSISTANT_CONTEXT_WINDOW_SIZE', 5))  
        print_intro_message()  
        if auth_type!=None:
            self.auth(auth_type)  
            self.create_clients()  
            self.load_plugins()  
            self.load_plugin_capabilities()
        self.workflow_list = {}
        self.load_workflows()
    def launch_auth(self,auth_type):
        self.auth(auth_type)  
        self.create_clients()  
        self.load_plugins()  
        self.load_plugin_capabilities()
    def retrievedsession(self,sessionId): 
        #REtrieve a beatufied session to be displayed in the UI
        return self.sessions[sessionId]

    def auth(self, auth_type):  
        """  
        Authenticate with Azure using different credential types based on the provided auth_type.  
        """  
        # Use different types of Azure Credentials based on the argument  
        if auth_type == "interactive":  
            self.credential = InteractiveBrowserCredential()  
        elif auth_type == "client_secret":  
            self.credential = ClientSecretCredential(  
                tenant_id=os.getenv('AZURE_TENANT_ID'),  
                client_id=os.getenv('AZURE_CLIENT_ID'),  
                client_secret=os.getenv('AZURE_CLIENT_SECRET')  
            )  
        else:  
            # Managed Identity to be used when running in Azure Serverless functions.  
            self.credential = DefaultAzureCredential()  
        # Force authentication to make the user login  
        print_info("Authenticating with Azure...")  
        try:  
            self.credential.get_token("https://management.azure.com/.default")  
            print_info("Authentication successful")  
        except Exception as e:  
            print_error(f"Authentication failed: {e}")  
            print_error("Only unauthenticated plugins can be used")  
    def create_clients(self):  
        """  
        Create clients to external platforms using environment variables.  
        """  
        subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')  
        resource_group_name = os.getenv('AZURE_RESOURCEGROUP_NAME')  
        workspace_name = os.getenv('AZURE_WORKSPACE_NAME')  
        workspace_id = os.getenv('AZURE_WORKSPACE_ID')  
          
        self.client_list["sentinel_client"] = SentinelClient(  
            self.credential, subscription_id, resource_group_name, workspace_name, workspace_id  
        )  
        azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')  
        api_key = os.getenv('AZURE_OPENAI_API_KEY')  
        model_name = os.getenv('AZURE_OPENAI_MODELNAME')  
          
        self.client_list["azure_openai_client"] = AzureOpenAIClient(api_key, azure_endpoint, model_name)  
        #Requires Mail.Read Application Permission if used with Service Principal
        self.client_list["graph_api_client"] = GraphAPIClient(  
            self.credential) 
    def load_capabilities(self):
        """  
        Load custom capabilities from the capabilities folder.  
        """  
        capabilities_folder = os.path.join(os.getcwd(), 'capabilities')
        custom_capabilities = {}
        for filename in os.listdir(capabilities_folder):
            if filename.endswith('.json'):
                filepath = os.path.join(capabilities_folder, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    print_debug(f"Loading custom capabilities from {filename}")
                    capabilities = json.load(f)
                    for capability in capabilities['custom_capabilities']:
                        plugin_name = capability['plugin_name']
                        if (plugin_name not in custom_capabilities):
                            custom_capabilities[plugin_name] = []
                        custom_capabilities[plugin_name].append(capability)
        return custom_capabilities

    def load_plugins(self):  
        """  
        Auto-load plugins from the plugins folder using configuration file.  
        """  
        self.plugin_list = {}
        
        # Load plugin configuration
        config_path = os.path.join(os.getcwd(), 'plugins_config.json')
        if not os.path.exists(config_path):
            print_error(f"Plugin configuration file not found: {config_path}")
            print_info("Falling back to manual plugin loading")
            self._load_plugins_manual()
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            custom_capabilities = self.load_capabilities()
            
            for plugin_config in config.get('plugins', []):
                try:
                    plugin_name = plugin_config['name']
                    print_plugin_debug("PluginLoader", f"Loading plugin: {plugin_name}")
                    
                    # Dynamically import the plugin module
                    module = importlib.import_module(plugin_config['module'])
                    plugin_class = getattr(module, plugin_config['class'])
                    
                    # Prepare initialization arguments
                    init_args = []
                    
                    # Add basic init parameters in the order specified
                    init_params = plugin_config['init_params']
                    init_args.append(init_params['name'])
                    init_args.append(init_params['description'])
                    init_args.append(init_params['plugintype'])
                    
                    # Add required clients
                    for client_name in plugin_config.get('clients', []):
                        if client_name in self.client_list:
                            init_args.append(self.client_list[client_name])
                        else:
                            print_error(f"Required client '{client_name}' not found for plugin '{plugin_name}'")
                            raise ValueError(f"Missing client: {client_name}")
                    
                    # Add environment-based parameters
                    env_params = plugin_config.get('env_params', {})
                    for param_name, env_config in env_params.items():
                        if isinstance(env_config, dict):
                            # Support type conversion based on config
                            env_var = env_config.get('var')
                            default_value = env_config.get('default', 'True')
                            param_type = env_config.get('type', 'string')
                            value = os.getenv(env_var, default_value)
                            
                            try:
                                if param_type == 'boolean':
                                    # Handle various truthy/falsy values
                                    # Ensure value is a string before calling .lower()
                                    str_value = str(value) if value is not None else 'false'
                                    init_args.append(str_value.lower() in ('true', '1', 'yes', 'on'))
                                elif param_type == 'int':
                                    init_args.append(int(value))
                                elif param_type == 'float':
                                    init_args.append(float(value))
                                else:
                                    init_args.append(value)
                            except (ValueError, AttributeError) as e:
                                print_error(f"Failed to convert parameter '{param_name}' with value '{value}' to type '{param_type}': {e}")
                                raise ValueError(f"Type conversion error for parameter '{param_name}'")
                        else:
                            # Backward compatibility: simple string mapping to env var (deprecated)
                            print_plugin_debug("PluginLoader", f"Warning: Using deprecated env_params format for '{param_name}'. Consider using structured format.")
                            value = os.getenv(env_config, 'True')
                            # Default to boolean conversion for backward compatibility with loadSchema
                            # Ensure value is a string before calling .lower()
                            str_value = str(value) if value is not None else 'false'
                            init_args.append(str_value.lower() in ('true', '1', 'yes', 'on'))
                    
                    # Add custom capabilities if plugin supports it
                    if plugin_config.get('custom_capabilities', False):
                        init_args.append(custom_capabilities.get(plugin_name, []))
                    
                    # Instantiate the plugin
                    plugin_instance = plugin_class(*init_args)
                    self.plugin_list[plugin_name] = plugin_instance
                    print_plugin_debug("PluginLoader", f"Successfully loaded plugin: {plugin_name}")
                    
                except Exception as e:
                    print_error(f"Failed to load plugin '{plugin_config.get('name', 'unknown')}': {e}")
                    print_error(f"Stacktrace: {traceback.format_exc()}")
                    
        except Exception as e:
            print_error(f"Error loading plugin configuration: {e}")
            print_info("Falling back to manual plugin loading")
            self._load_plugins_manual()
    
    def _load_plugins_manual(self):
        """
        Manual plugin loading as fallback (original hardcoded implementation).
        """
        from app.plugins.GraphAPIPlugin import GraphAPIPlugin  
        from app.plugins.SentinelKQLPlugin import SentinelKQLPlugin  
        from app.plugins.GPTPlugin import GPTPlugin  
        from app.plugins.FetchURLPlugin import FetchURLPlugin
        
        loadSchema=(os.getenv('SENTINELKQL_LOADSCHEMA', 'True')=='True' )
        custom_capabilities = self.load_capabilities()
        self.plugin_list = {  
            "GraphAPIPlugin":GraphAPIPlugin(  
                "GraphAPIPlugin", "Plugin to retrieve data from the Microsoft GraphAPI", "API", self.client_list["graph_api_client"]
            ),
            "SentinelKQLPlugin": SentinelKQLPlugin(  
                "SentinelKQLPlugin", "Plugin to generate and run KQL queries in Sentinel", "API",   
                self.client_list["azure_openai_client"], self.client_list["sentinel_client"], loadSchema, custom_capabilities.get("SentinelKQLPlugin", [])
            ),  
            "FetchURLPlugin": FetchURLPlugin(  
                "FetchURLPlugin", "Plugin to fetch HTML sites", "API",   
                self.client_list["azure_openai_client"]  
            ),  
            "GPTPlugin": GPTPlugin(  
                "GPTPlugin", "Plugin to run prompts in Azure OpenAI GPT models", "GPT",   
                self.client_list["azure_openai_client"]  
            )  
        }  
    def load_plugin_capabilities(self):
        self.plugin_capabilities=[]
        for plugin_name in self.plugin_list.keys():
            plugincapability=self.plugin_list[plugin_name].plugincapabilities()
            plugin={
                "plugin_name":plugin_name,
                "capabilities":plugincapability
            }
            self.plugin_capabilities.append(plugin)
    def load_workflows(self):
        """  
        Load workflows from the workflows folder.  
        """  
        workflows_folder = os.path.join(os.getcwd(), 'workflows')
        for filename in os.listdir(workflows_folder):
            if filename.endswith('.json'):
                filepath = os.path.join(workflows_folder, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
                    self.workflow_list[workflow['workflow']['shortcut'].lower()] = workflow
    def get_workflow(self, shortcut):
        """  
        Get the workflow by its shortcut.  
        """  
        return self.workflow_list.get( shortcut.lower(), None)
    


    def decompose_in_tasks(self, sessionId,prompt, channel):  
        """  
        Select the appropriate plugin based on the input prompt.  
        """  
        # System message to guide the AI assistant on how to decompose the prompt into tasks
        system_message = replace_template_placeholders("Core.Decompose.System", AgentCapabilities=self.plugin_capabilities)
        
        # User prompt to be decomposed into tasks
        extended_user_prompt = replace_template_placeholders("Core.Decompose.User", UserPrompt=prompt)
        
        # Create a new session with the system message and the current session
        system_object = {"role":"system","content":[{"type":"text","text":system_message}]}
        new_session = []
        new_session.append(system_object)

        new_session_object = {"messages":new_session + self.sessions[sessionId]["messages"][1:]}
        
        
        # Run the prompt through the GPTPlugin to get the task list
        task={'plugin_name':'Core','capability_name':'Decompose'}
        task["task"]=extended_user_prompt
        task_list_object = self.plugin_list["GPTPlugin"].runtask(task, new_session_object)
        task_list_object['session_tokens']=self.update_tokens_scope(task_list_object['session_tokens'], 'Core-Decompose')
        # Handle errors in the task list generation
        if task_list_object['status'] == 'error':
            channel('systemmessage', {"message": f"Error: {task_list_object['result'] }"})
            return []   
        else:
            # Clean tags from the result
            selected_plugin_string_clean = task_list_object['result'].replace("```plaintext", "").replace("```json", "").replace("```html", "").replace("```", "")  
            try:
                # Parse the cleaned result into a JSON object
                obj = json.loads(selected_plugin_string_clean) 
            except:
                # Handle JSON parsing errors by defaulting to using the GPTPlugin
                channel('systemmessage', {"message": f"Error: {'Error Decomposing. Running User Prompt with GPT Plugin' }"})
                obj = [{"plugin_name": "GPTPlugin", "capability_name": "runprompt", "task": prompt}]
            task["task"]=prompt
            task['response_object']=task_list_object
            task['processed_response']={"status": "N/A", "result": "N/A","prompt":"N/A","session_tokens":[]} 
            self.update_session(sessionId,task,addToMessages=False) 
            return obj
    def run_prompt(self, sessionId,output_type, prompt, channel=None):  
        """  
        Run the provided prompt using task decomposition or workflow.  
        """  
        if self.sessions.get(sessionId) is None:
            self.sessions[sessionId]={"id":sessionId,"tasks":[],"messages": [{"role":"system","content": [{"type": "text", "text":TeisecPrompts["Core.Main.System"]}]}] ,"session_tokens":[]}
        if prompt.startswith('/'):
            shortcut = prompt[1:].split(' ')[0]
            workflow = self.get_workflow(shortcut)
            if workflow:
                self.send_system(channel, {"message": f"Running workflow: {workflow['workflow']['title']}"} )
                return self.run_workflow(sessionId, workflow, prompt,output_type, channel)
            else:
                self.send_system(channel, {"message": f"Workflow shortcut '{shortcut}' not found."})
                return []
        else:
            return self.decompose_and_run_prompt(sessionId,output_type, prompt, channel)

    def decompose_and_run_prompt(self, sessionId,  output_type, prompt, channel=None):
        """  
        Run the provided prompt using task decomposition.  
        """  
        start_time = time.time()  
        task_results = []
        decomposed_tasks = self.decompose_in_tasks(sessionId,prompt, channel)
        self.send_system(channel, {"message": 'Prompt decomposed in ' + str(len(decomposed_tasks)) + ' tasks'})
        for task in decomposed_tasks:
            self.send_system(channel, {"message": '(' + task['plugin_name'] + '-' + task['capability_name'] + ') ' + task['task']})
            executed_task=self.run_task(task,sessionId,output_type,channel)
            self.update_session(sessionId,executed_task)
            task_results.append(executed_task)  
            self.send_response(channel, {"message": executed_task['processed_response']['result']})      
        self.stop_timer(start_time, channel)
        return task_results
    def run_workflow(self, sessionId,workflow, prompt, output_type, channel=None):
        """  
        Run the provided workflow.  
        """  
        start_time = time.time()  
        task_result_list = []
        parameters_object={'parameters_found':'yes','parameters':{}}
        if 'input_parameters' in workflow['workflow'] and workflow['workflow']['input_parameters']!=[]:
            parameters_result_object = self.extract_parameters(sessionId,workflow['workflow']['input_parameters'], prompt, channel)
            parameters_object=parameters_result_object['result']
            task={'plugin_name':'Core','capability_name':'Core-Workflow-InputParameters','task':prompt}
            parameters_result_object['session_tokens']=self.update_tokens_scope(parameters_result_object['session_tokens'], 'Core-Workflow-InputParameters')
            task['response_object']=parameters_result_object
            task['processed_response']={"status": "N/A", "result": "N/A","prompt":"N/A","session_tokens":[]}
            self.update_session(sessionId,task,addToMessages=False) 
        if parameters_object['parameters_found'] == "yes":
            for workflow_task in workflow['workflow']['tasks']:
                tasks_to_run=[]
                if 'parallel_tasks' in workflow_task:
                    tasks_to_run.extend(workflow_task['parallel_tasks'])
                    self.send_system(channel, {"message": 'Workflow-Running Parallel Tasks (' + str(len(workflow_task['parallel_tasks'])) + ')'})
                else:
                    tasks_to_run.append(workflow_task)
                prepared_tasks=[]
                for task_to_run in tasks_to_run:
                    task=self.prepare_workflow_task( task_to_run,parameters_object)
                    prepared_tasks.append(task)
                task_results=self.run_parallel_workflow(sessionId,prepared_tasks,output_type,channel)
                for task_result in task_results:
                    try:
                        self.send_system(channel, {"message": '(' + task_result['plugin_name'] + '-' + task_result['capability_name'] + ') ' + task_result['task']})
                        self.update_session(sessionId,task_result)
                        if task_result['response_object']['status'] == 'error':
                            channel('systemmessage', {"message": f"Error: {task_result['response_object']['result'] }"})   
                        self.send_response(channel, {"message": task_result['processed_response']['result']})   
                        task_result_list.append(task_result)
                    except:
                        print_error(f"Stacktrace: {traceback.format_exc()}")
                        self.send_system(channel, {"message": "Error: Error processing Task result in the workflow." })
                        self.send_system(channel, {"message": task_result})

        else:
            self.send_system(channel, {"message": "Error: Required Workflow parameters not found in the prompt or session."})
        self.stop_timer(start_time, channel)
        return task_result_list
    def run_parallel_workflow(self,sessionId, tasklist,output_type='html', channel=None):
        results = []  
        # Using ThreadPoolExecutor to process items in parallel  
        with concurrent.futures.ThreadPoolExecutor( max_workers=10) as executor:  
            # Create a partial function with the channel and outputtype parameters
            run_task_with_params = partial(self.run_task,sessionId=sessionId,output_type=output_type, channel=channel)
            # Map the processing function to the items and collect the results  
            for result in executor.map(run_task_with_params, tasklist):  
                results.append(result)
        return results 
    def prepare_workflow_task(self, workflow_task,parameters_object):
        # Replace the parameters in the task prompt
        task_prompt = workflow_task['prompt_text']
        for param_name, param_value in parameters_object['parameters'].items():
            task_prompt = task_prompt.replace(f"{{{{{param_name}}}}}", param_value)
        task = {
            "plugin_name": workflow_task['plugin_name'],
            "capability_name": workflow_task['capability_name'],
            "task": task_prompt
        }
        return task
    
    def run_task(self, task,sessionId, output_type ,channel=None):
        #get plugin and Capability
        plugin_name=task['plugin_name']
        try:
            plugin=self.get_plugin(plugin_name)
            capability=plugin.plugincapabilities()[task['capability_name']]
        except:
            task['response_object']= {"status": "error", "result": f"Error: Plugin or Capability {task['capability_name']} not found.","prompt":task['task'],"session_tokens":[]}    
            task_response_object = self.process_task_response(task,output_type)
            task['processed_response']= task_response_object 
            return task
        #check if capabilitiy has input parameters
        task['extracted_parameters']={'result':{'parameters_found':'yes','parameters':{}},'session_tokens':[]}  
        if 'parameters' in capability and capability['parameters']!=[]:
            #extract parameters
            task['extracted_parameters']=self.extract_parameters(sessionId,capability['parameters'],task['task'],channel)
        #run task with plugin capability
        try:
            task_response_object = plugin.runtask(task, self.sessions[sessionId])
            task['response_object']=task_response_object
        except Exception as e:
            print_error(f"Error in task execution: {e}\n{traceback.format_exc()}")
            task['response_object']= {"status": "error", "result": f"Error in task execution: {e}","prompt":task['task'],"session_tokens":[]}            
        task_response_object = self.process_task_response(task,output_type)
        task['processed_response']= task_response_object        
        return task
    
    def process_task_response(self, task, output_type):
        processed_output_object = self.process_output(output_type, task['response_object']['prompt'], str(task['response_object']['result']))   
        return processed_output_object
    def process_output(self, output_type, user_input, response):  
        """  
        Process the response to format it for specific output types (Terminal, HTML, etc.).  
        """  
        if output_type == 'terminal':  
            extended_prompt = replace_template_placeholders("Core.Output.Terminal", UserInput=user_input, Response=response)  
        elif output_type == 'html':  
            extended_prompt = replace_template_placeholders("Core.Output.HTML", UserInput=user_input, Response=response)    
        elif output_type == 'other':  
            extended_prompt = replace_template_placeholders("Core.Output.Other", UserInput=user_input, Response=response)  
        task={}
        task["task"]=extended_prompt
        prompt_result_object = self.plugin_list["GPTPlugin"].runtask(task, {"messages":[]})
        return self.clean_prompt_result(prompt_result_object)
    def clean_prompt_result(self, prompt_result_object):  
        """
        remove Prompt result tags and return the result"""
        prompt_result_object['result'] = prompt_result_object['result'].replace("```plaintext", "").replace("```kusto", "").replace("```json", "").replace("```html", "").replace("```", "")  
        return prompt_result_object  
      
   
    def extract_parameters(self, sessionId, parameters, prompt, channel):
        """  
        Extract and replace the input parameters from the user prompt and the current session.  
        """  
        extended_prompt = replace_template_placeholders("Core.ExtractParameters.System", UserInput=prompt, Parameters=parameters)  
        task={}
        task["task"]=extended_prompt
        parameters_result_object = self.plugin_list["GPTPlugin"].runtask(task, self.sessions[sessionId])
        #self.update_session_usage(parameters_result_object['session_tokens']) 
        parameters_result_object = self.clean_prompt_result(parameters_result_object)
        try:
            # Parse the cleaned result into a JSON object
            parsed_obj = json.loads(parameters_result_object['result'])
            parameters_result_object['result']=parsed_obj
        except:
            # Handle JSON parsing errors
            channel('systemmessage', {"message": f"Error: {'Error generating parameters.'}"})
            obj = {}
            parameters_result_object['result']=obj
        return parameters_result_object
    def update_session(self,sessionId, task,addToMessages=True):  
        """  
        Update the session with the latest prompt and response.  
        """
        self.sessions[sessionId]["tasks"].append(task)    
        if addToMessages:
            user_object = {"role": "user", "content": [{"type": "text", "text": task['response_object']['prompt']}]}  
            assistant_object = {"role": "assistant", "content": [{"type": "text", "text": str(task['response_object']['result'])}]}  
            # Maintain a sliding window of messages (system message + context_window_size pairs)
            # Each pair is a user message and an assistant message
            # Before adding new messages, check if we need to remove old ones
            max_messages = (self.context_window_size * 2) + 1  # +1 for system message
            if len(self.sessions[sessionId]["messages"]) > max_messages - 2:  # -2 because we're about to add 2 messages
                self.sessions[sessionId]["messages"].pop(1)  # Remove the oldest user message
                self.sessions[sessionId]["messages"].pop(1)  # Remove the oldest assistant message
            self.sessions[sessionId]["messages"].append(user_object)  
            self.sessions[sessionId]["messages"].append(assistant_object)  
            self.update_session_usage(sessionId,task['response_object']['session_tokens'], scope='Plugin-Internal')  
            self.update_session_usage(sessionId,task['processed_response']['session_tokens'], scope='Core-OutPutProcessing')
        
        # Prevent unbounded growth of tasks array - keep only recent tasks
        max_tasks = 50  # Keep last 50 tasks
        if len(self.sessions[sessionId]["tasks"]) > max_tasks:
            self.sessions[sessionId]["tasks"] = self.sessions[sessionId]["tasks"][-max_tasks:]
    def update_tokens_scope(self,session_tokens, scope):
        uptaded_session_tokens = session_tokens
        if scope != '':
            uptaded_session_tokens = []
            for token in session_tokens:
                token['scope'] = scope
                uptaded_session_tokens.append(token)
        return uptaded_session_tokens
    def update_session_usage(self,sessionId, session_tokens,scope='Core'):
        # Update the session tokens with the latest usage
        uptaded_session_tokens = self.update_tokens_scope(session_tokens, scope)
        self.sessions[sessionId]["session_tokens"]=self.sessions[sessionId]["session_tokens"]+uptaded_session_tokens
    def clear_session(self):  
        """  
        Clear the current session.  
        """  
        print_info("New Session Created")  
        sessionId=str(uuid.uuid4())
        self.sessions[sessionId]={"id":sessionId,"tasks":[],"messages": [{"role":"system","content": [{"type": "text", "text":TeisecPrompts["Core.Main.System"]}]}] ,"session_tokens":[]}
        return sessionId
    def stop_timer(self, start_time, channel):  
        # Stop the timer  
        end_time = time.time()  
        # Calculate the elapsed time  
        elapsed_time = round(end_time - start_time)
        self.send_system(channel, {"message": f"Processing Time: {elapsed_time} seconds"}) 
    
    def get_plugin(self, plugin_name):  
        """  
        Get the plugin instance by its ID.  
        """  
        return self.plugin_list[plugin_name]  

    def send_system (self,channel,system_object):
        if channel is not None:
            channel('systemmessage',system_object)
    def send_debug (self,channel,debug_object):
        if channel is not None:
            channel('debugmessage',debug_object)
    def send_response (self,channel,response_object):
        if channel is not None:
            channel('resultmessage',response_object)