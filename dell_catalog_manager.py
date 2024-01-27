import re
from packaging_legacy.version import LegacyVersion
import requests
from cache import CachedAPI
import settings
from tools import generate_random_user_agent
import os.path
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import patoolib
from patoolib.util import PatoolError


class DellCatalogManager(CachedAPI):
    def __init__(self, cache_time_hours=6):

        self.catalog_name = 'CatalogPC.cab'
        self.extracted_catalog_name = 'CatalogPC.xml'

        self.catalog_filepath = os.path.join(settings.DATA_DIR, self.catalog_name)
        self.extracted_catalog_filepath = os.path.join(settings.DATA_DIR, self.extracted_catalog_name)

        self.catalog_cache_file = os.path.join(settings.DATA_DIR, 'CatalogPC.json')
        super().__init__(self.catalog_cache_file, cache_time_hours * 60)

        self.base_url = "https://downloads.dell.com"

        self.cache_key = os.path.join(self.base_url, self.catalog_name)

        self.headers = {
            'User-Agent': generate_random_user_agent(),
        }

    def make_request(self, url, method='GET', params=None, data=None, return_json=False, **kwargs):
        """
        Make an HTTP request to the API.

        :param url: The request URL.
        :param method: The HTTP method of the request. Defaults to 'GET'.
        :param params: The query parameters for the request.
        :param data: The body data for the request. Used with 'POST', 'PUT', etc.
        :param return_json: Return the request as json format
        :return: The data returned by the request, or None in case of an error.
        """
        try:
            response = requests.request(method, url, params=params, headers=self.headers, json=data, **kwargs)
            response.raise_for_status()
            if return_json:
                return response.json()
            return response
        except Exception as e:
            print(f"Request error: {e}")
        return None

    def download_file(self, url, destination=None, filename=None):
        try:
            response = self.make_request(url, stream=True)
            if filename is None:
                content_disposition = response.headers.get('content-disposition')
                if content_disposition:
                    filename = re.findall("filename=(.+)", content_disposition)[0]
                    filename = unquote(filename)  # Handle URL-encoded characters in filename
                else:
                    # Fallback to extracting from the URL
                    filename = url.split("/")[-1]

            if destination is None:
                filepath = os.path.join(settings.DATA_DIR, filename)
            else:
                filepath = os.path.join(destination, filename)

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            return True

        except Exception as e:
            print(f"An error occurred while downloading {filename if filename else 'the file'} : {e}")
            return False

    def download_catalog(self):
        downloaded = False
        for filename in [self.catalog_name]:
            download_url = f"{self.base_url}/catalog/{filename}"
            success = self.download_file(download_url, settings.DATA_DIR)
            if success:
                downloaded = True
        return downloaded

    def extract_cab_file(self):
        try:
            if patoolib.is_archive(self.catalog_filepath):
                patoolib.extract_archive(self.catalog_filepath, outdir=settings.DATA_DIR)
                return True
            else:
                print("This is not an archive !")
                return False

        except PatoolError as e:
            print(f"An error occurred, impossible to extract dell catalog ! ({e})")
            return False

    def load_xml_catalog(self):

        try:
            if self.download_catalog() and self.extract_cab_file():
                xml_catalog = ET.parse(self.extracted_catalog_filepath)
                xml_catalog_tree = xml_catalog.getroot()
                return xml_catalog_tree

            return None

        except Exception as e:
            print(f"An unknown error occurred: {e}")
            return None

    def get_catalog(self):
        return self.get_cached_data(self.cache_key, self.extract_software_components)

    def extract_software_components(self, only_model_name=False):

        def is_duplicate(entry, entry_list):
            return any(entry == existing_entry for existing_entry in entry_list)

        catalog = self.load_xml_catalog()
        if not catalog:
            return {}

        data = {}
        model_data = {}

        for software_component in catalog.findall("SoftwareComponent"):
            component_type_display = software_component.find("ComponentType/Display").text.lower()
            brand_element = software_component.find("SupportedSystems/Brand")
            brand_display = brand_element.find("Display").text.lower()

            for model_element in brand_element.findall("Model"):
                model_display = model_element.find("Display").text.lower()
                model_display = model_display.replace(f"{brand_display}-", "", 1)

                # Ajout des noms de modèles à model_data
                if brand_display not in model_data:
                    model_data[brand_display] = []
                if model_display not in model_data[brand_display]:
                    model_data[brand_display].append(model_display)

                if not only_model_name:

                    name = software_component.find('Name/Display').text
                    description = software_component.find('Description/Display').text
                    url = software_component.find("ImportantInfo").attrib.get('URL')

                    if brand_display not in data:
                        data[brand_display] = {}

                    if model_display not in data[brand_display]:
                        data[brand_display][model_display] = {}

                    if component_type_display not in data[brand_display][model_display]:
                        data[brand_display][model_display][component_type_display] = []

                    new_entry = {
                        'name': name,
                        'description': description,
                        'url': url
                    }

                    new_entry.update(software_component.attrib)

                    if 'path' in new_entry:
                        new_entry['download_url'] = f"{self.base_url}/{new_entry['path']}"
                        new_entry.pop('path')

                    if 'schemaVersion' in new_entry:
                        new_entry.pop('schemaVersion')

                    if not is_duplicate(new_entry, data[brand_display][model_display][component_type_display]):
                        data[brand_display][model_display][component_type_display].append(new_entry)

        if only_model_name:
            save_data = model_data
        else:
            save_data = data

        return save_data

    def find_bios_files(self, brand, model, latest=False):
        """Find BIOS files for a specific machine by its brand and model."""
        catalog = self.get_catalog()

        brand = brand.lower()
        model = model.lower()

        if catalog is None:
            return None

        try:
            bios_entries = catalog[brand][model]['bios']

            if latest and bios_entries:
                latest_bios_entry = max(bios_entries, key=lambda x: LegacyVersion(x['vendorVersion']))
                return latest_bios_entry

            return bios_entries

        except KeyError:
            print(f"No BIOS files found for brand: {brand}, model: {model}")
            return None

    def update_bios(self, brand, model):

        local_brand_storage = os.path.join(settings.BIOS_REPO_DIR, brand)
        if not os.path.exists(local_brand_storage):
            os.makedirs(local_brand_storage, exist_ok=True)

        latest_bios = self.find_bios_files(brand, model, latest=True)

        if latest_bios is None:
            print(f"No BIOS found for {brand} brand and {model} model.")
            return

        latest_version = latest_bios['dellVersion']
        latest_filename = f"{brand}_{model}[{latest_version}].exe"

        if latest_filename in os.listdir(local_brand_storage):
            print(f"Latest BIOS version ({latest_version}) is already downloaded for {brand} {model}")
            return False

        download_url = latest_bios['download_url']
        print(f"Downloading latest BIOS version ({latest_version}) for {brand} {model} ...")
        downloaded = self.download_file(download_url, local_brand_storage, latest_filename)

        if downloaded:
            print(f"Latest BIOS version ({latest_version}) for {brand} {model} downloaded successfully.")
            return True

        print(f"Latest BIOS version ({latest_version}) for {brand} {model} cannot be downloaded ...")
        return


def parse_existing_bios_files(bios_repo_base_dir):
    bios_files_info = {}
    for brand in os.listdir(bios_repo_base_dir):

        brand_path = os.path.join(bios_repo_base_dir, brand)
        if os.path.isdir(brand_path):

            bios_files_info[brand] = {}
            for filename in os.listdir(brand_path):
                match = re.match(r'(.+)\[(.+)]\.exe', filename)

                if match is None:
                    print(f"Could not parse filename: {filename}")
                    continue

                full_model, version = match.groups()
                model = full_model.split('_')[-1]

                if model not in bios_files_info[brand]:
                    bios_files_info[brand][model] = []

                bios_files_info[brand][model].append(version)

            # Sort versions for each model in descending order
            for model in bios_files_info[brand]:
                bios_files_info[brand][model] = sorted(bios_files_info[brand][model],
                                                       key=lambda x: LegacyVersion(x), reverse=True)

    return bios_files_info


def check_and_update_bios(dell_catalog_manager, bios_repo_base_dir):
    existing_bios_files = parse_existing_bios_files(bios_repo_base_dir)
    for brand, models in existing_bios_files.items():
        for model, versions in models.items():

            catalog_brand = brand  # Example: convert to the appropriate format if needed
            catalog_model = model  # Example: convert to the appropriate format if needed

            latest_bios = dell_catalog_manager.find_bios_files(catalog_brand, catalog_model, latest=True)
            latest_version = latest_bios['dellVersion'] if latest_bios else None
            existing_latest_version = versions[0]

            if latest_version and LegacyVersion(latest_version) > LegacyVersion(existing_latest_version):
                print(f"Updating BIOS for {brand} {model} from {existing_latest_version} to {latest_version}")

                download_url = latest_bios['download_url']
                filename = f"{brand}_{model}[{latest_version}].exe"

                brand_filedir = os.path.join(bios_repo_base_dir, brand)
                dell_catalog_manager.download_file(download_url, brand_filedir, filename)


dell_catalog_manager = DellCatalogManager()

# result = dell_catalog_manager.find_bios_files('Optiplex', '3070', latest=True)
# result = dell_catalog_manager.find_bios_files('Precision', 'T3620', latest=True)
# result = dell_catalog_manager.find_bios_files('Latitude', '3190', latest=True)
result = dell_catalog_manager.find_bios_files('Optiplex', '3010', latest=True)
print(result)

dell_catalog_manager.update_bios('OptiPlex', '7010')

# print(parse_existing_bios_files(BIOS_REPO_DIR))

# check_and_update_bios(dell_catalog_manager, BIOS_REPO_DIR)

# dell_catalog_manager.extract_software_components(only_model_name=True, destination='test_catalog.json')
