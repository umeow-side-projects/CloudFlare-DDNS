import json
import argparse

import os.path
import urllib.request

class APIError(Exception):
    pass

class APIClient:
    BASE_URL = 'https://api.cloudflare.com/client/v4'
    def __init__(self, config: dict) -> None:
        if not config['api_token']:
            raise KeyError('config key `api_token` not exist!')
        
        self.api_token = config['api_token']
        self._api_header = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        self.ipv4 = self._get_ipv4()
        

    def _api_query(self, path, data=None, method=None):
        req = urllib.request.Request(f'{APIClient.BASE_URL}{path}', data=data, headers=self._api_header, method=method)
        res = urllib.request.urlopen(req)
        response_json = json.loads(res.read())
        
        if not response_json['success']:
            return APIError(f'API Query Failed!\n {response_json}')
        
        return response_json
    
    def _get_ipv4(self):
        req = urllib.request.Request('https://api.ipify.org?format=json')
        res = urllib.request.urlopen(req)
        
        return json.loads(res.read())['ip']

    def get_zones(self):
        return self._api_query('/zones')
    
    def get_zone_records(self, zone_id):
        return self._api_query(f'/zones/{zone_id}/dns_records')
    
    def update_zone_record(self, zone_id, data):
        method = 'POST'
        record = {
            'comment': 'Create By CloudFlare-DDNS',
            'content': self.ipv4,
            'name': data['name'],
            'proxied': data['proxied'],
            'type': 'A',
            'ttl': 3600,
        }
        path = f'/zones/{zone_id}/dns_records'
        
        if 'record_id' in data:
            method = 'PATCH'
            path += f'/{data['record_id']}'
        
        return self._api_query(path, data=json.dumps(record).encode('utf-8'), method=method)

def main(config_path) -> None:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config file `{config_path}` not exist!')

    with open(config_path, 'rb') as f:
        config = json.load(f)
    
    api_client = APIClient(config)
    zones = api_client.get_zones()
    
    zones_id = {}
    subdomains = {}
    
    for zone in zones['result']:
        zones_id[zone['name']] = zone['id']
        subdomains[zone['name']] = {}
    
    for subdomain in config['subdomains']:
        if subdomain['domain'] not in zones_id:
            raise KeyError(f'Couldn\'t found domain `{subdomain['domain']}` from `{config_path}`')
        
        if not isinstance(subdomain['name'], str):
            raise TypeError(f'Subdomain name should be str! {subdomain['name']} from `{config_path}`')
        
        if subdomain['name'] == '@':
            subdomains[subdomain['domain']][f'{subdomain['domain']}'] = {
                'name': f'{subdomain['domain']}',
                'proxied': subdomain.get('proxied', False)
            }
        else:
            subdomains[subdomain['domain']][f'{subdomain['name']}.{subdomain['domain']}'] = {
                'name': f'{subdomain['name']}.{subdomain['domain']}',
                'proxied': subdomain.get('proxied', False)
            }
    
    for domain, zone_id in zones_id.items():
        zone_detail = api_client.get_zone_records(zone_id)
        
        for record in zone_detail['result']:
            if record['name'] not in subdomains[domain]:
                continue
            
            subdomains[domain][record['name']]['record_id'] = record['id']
            
            if record['content'] == api_client.ipv4:
                del subdomains[domain][record['name']]
    
    for domain, d in subdomains.items():
        for _name, record in d.items():
            api_client.update_zone_record(zones_id[domain], record)
            print(f'Updating domain `{record['name']}` to `{api_client.ipv4}`...')
    
    print('all done!')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    
    parser.add_argument('-c', '--config', type=str, help='target config file ex. `config.json`')
    
    args = parser.parse_args()
    
    config_file = args.config
    
    if config_file is None:
        config_file = 'config.json'
        print('Because not provide -c or --config, Using default config file `config.json`')
    
    print(f'Config: `{config_file}`\n')
    main(config_file)