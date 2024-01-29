import re
import tempfile
from packaging_legacy.version import LegacyVersion
import requests
from cache import CachedAPI
import settings
from tools import generate_random_user_agent, load_xml_file, extract_cab_file
import os.path
from urllib.parse import unquote

#
# All : https://downloads.dell.com/catalog/CatalogPC.cab
#
# https://downloads.dell.com/catalog/CatalogIndexPC.cab
# -> Optiplex 3060 :
#      -> https://downloads.dell.com/FOLDER11176103M/1/Optiplex_085F.cab


class DellCatalogManager(CachedAPI):
    def __init__(self, cache_time_hours=6):

        self.catalog_cache_file = os.path.join(settings.DATA_DIR, 'CatalogCache.json')
        super().__init__(self.catalog_cache_file, cache_time_hours * 60)

        self.base_url = "https://downloads.dell.com"
        self.catalog_url = f"{self.base_url}/catalog/CatalogPC.cab"

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

    def download_file(self, url, destination, filename=None):
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

            filepath = os.path.join(destination, filename)

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            return filename

        except Exception as e:
            print(f"An error occurred while downloading {filename if filename else 'the file'} : {e}")
            return False

    def download_cab_and_load_xml_file(self, url):

        # At the end it's delete the tmp folder
        with tempfile.TemporaryDirectory() as tmp_dir:
            print('created temporary directory', tmp_dir)

            full_filename = self.download_file(url, tmp_dir)
            filepath = os.path.join(tmp_dir, full_filename)

            # If the download is a success
            if full_filename:
                filename, file_extension = os.path.splitext(full_filename)
                xml_file_path = os.path.join(tmp_dir, filename + '.xml')
                extract_cab_file(filepath, tmp_dir)
                return load_xml_file(xml_file_path)

    def get_catalog(self):
        return self.get_cached_data(self.catalog_url, self.extract_software_components)

    def extract_software_components(self, only_model_name=False):
        def is_duplicate(entry, entry_list):
            return any(entry == existing_entry for existing_entry in entry_list)

        catalog = self.download_cab_and_load_xml_file(self.catalog_url)

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


def download_latest_bios(self, brand, model):
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


def delete_old_bios_version(brand, model, versions_to_delete: list):
    brand_dir = os.path.join(settings.BIOS_REPO_DIR, brand)
    for v in versions_to_delete:

        filename = f"{brand}_{model}[{v}].exe"
        filepath = os.path.join(brand_dir, filename)

        if os.path.exists(filepath):
            print(f"Deleting old bios version ({v}) for {brand} {model} ")
            os.remove(filepath)


def check_and_update_bios(dell_catalog_manager):
    existing_bios_files = parse_existing_bios_files(settings.BIOS_REPO_DIR)
    for brand, models in existing_bios_files.items():
        for model, versions in models.items():

            latest_bios = dell_catalog_manager.find_bios_files(brand, model, latest=True)
            if latest_bios:
                latest_version = latest_bios['dellVersion'] if latest_bios else None
                existing_latest_version = versions[0]

                if latest_version and LegacyVersion(latest_version) > LegacyVersion(existing_latest_version):
                    print(f"Updating BIOS for {brand} {model} from {existing_latest_version} to {latest_version}")
                    dell_catalog_manager.download_latest_bios(brand, model)
                else:
                    print(f"{brand} {model} is already on the latest BIOS version ({latest_version})")

            # Deleting Old version
            # versions_to_delete = versions[1:]
            # print(f"Version to delete : {versions_to_delete}")
            # delete_old_bios_version(brand, model, versions_to_delete)


if __name__ == "__main__":
    dell_catalog_manager = DellCatalogManager()

    # result = dell_catalog_manager.find_bios_files('Optiplex', '3070', latest=True)
    # result = dell_catalog_manager.find_bios_files('Precision', 'T3620', latest=True)
    # result = dell_catalog_manager.find_bios_files('Latitude', '3190', latest=True)
    # result = dell_catalog_manager.find_bios_files('Optiplex', '3010', latest=True)

    # dell_catalog_manager.update_bios('OptiPlex', '7010')
    # dell_catalog_manager.update_bios('OptiPlex', '3010')
    # dell_catalog_manager.update_bios('OptiPlex', '3020')

    # print(parse_existing_bios_files(settings.BIOS_REPO_DIR))

    # check_and_update_bios(dell_catalog_manager)

    print(dell_catalog_manager.get_catalog())

    # dell_catalog_manager.extract_software_components(only_model_name=True, destination='test_catalog.json')
