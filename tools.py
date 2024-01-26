import json
from fake_useragent import UserAgent

def save_request_as_json(output, destination_file, save_encoding='utf-8'):
    output = json.dumps(output, indent=4)

    with open(destination_file, 'w', encoding=save_encoding) as file:
        file.write(output)

def get_json_content(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)
    
def generate_random_user_agent():
    ua = UserAgent(browsers=['chrome', 'firefox', 'edge'])
    random_user_agent = ua.random
    return random_user_agent