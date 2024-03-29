import json
import re
import chardet
import xml.etree.ElementTree as ET
import patoolib
from fake_useragent import UserAgent
from patoolib.util import PatoolError


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


def load_xml_file(filepath):
    # Detect the encoding of the XML file
    with open(filepath, 'rb') as file:
        detector = chardet.universaldetector.UniversalDetector()
        for line in file.readlines():
            detector.feed(line)
            if detector.done:
                break
        encoding = detector.result['encoding']

    # Read the XML file
    with open(filepath, 'r', encoding=encoding) as file:
        xml_data = file.read()

    # Remove the entire xmlns attribute using regular expressions
    modified_xml_data = re.sub(r'\s?xmlns="[^"]+"', '', xml_data)

    # Parse the modified XML
    return ET.fromstring(modified_xml_data)


def extract_cab_file(filepath, destination):
    try:
        # Extract the archive
        if patoolib.is_archive(filepath):
            print(f'Extracting the archive ...')
            patoolib.extract_archive(filepath, outdir=destination, verbosity=-1)
            print(f'Done !')
            return True
        else:
            print("This is not an archive !")
            return

    except PatoolError as e:
        print(f"An error occurred, impossible to extract the cab file ! ({e})")
        return
