import logging

import zeep

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

wsdl = 'wsdl/RcWareDbAccess.wsdl'
settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)
client = zeep.Client(wsdl=wsdl, settings=settings)

comm_status = '839DCBB6-55BB-4CB3-BE01-F242E0B3EAC1'

print('Alive:', client.service.ServerAlive())

creds = {
    'Name': username,
    'Password': password
}
print('Check Creds:', client.service.CheckCredentials(creds))

factory = client.type_factory('http://schemas.datacontract.org/2004/07/ESG.Db.Server.Shared')

kvp = factory.KeyValuePair(IsKey=True, Key='DPGuid', Value='839DCBB6-55BB-4CB3-BE01-F242E0B3EAC1')
akvp = factory.ArrayOfKeyValuePair(kvp)
aakvp = factory.ArrayOfArrayOfKeyValuePair(akvp)

creds = factory.Credentials(Name=username, Password=password)

res = client.service.GetData(
    creds,
    aakvp,
    '2020-01-08T10:00:00Z',
    '2020-01-08T12:00:00Z',
    0,
    3000,
    0,
    10,
)

print(res)
