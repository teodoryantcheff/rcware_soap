import csv
import logging

import zeep

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

wsdl = 'wsdl/RcWareDbAccess.wsdl'
settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)

# Available ports are HistoryAccess, HistoryAccessGZip, HistoryAccess1. Only HistoryAccess seems to be alive.
client = zeep.Client(wsdl=wsdl, settings=settings, port_name='HistoryAccess')

comm_status = '839DCBB6-55BB-4CB3-BE01-F242E0B3EAC1'

print('Alive:', client.service.ServerAlive())

creds = {
    'Name': username,
    'Password': password
}
print('Check Creds:', client.service.CheckCredentials(creds))
# print('Check Creds:', client.service.CheckCredentials(Name=username, Password=password))

factory = client.type_factory('http://schemas.datacontract.org/2004/07/ESG.Db.Server.Shared')

kvp = factory.KeyValuePair(IsKey=True, Key='DPGuid', Value='C4C1EDF3-BACD-4552-9323-92E57D326907')
akvp = factory.ArrayOfKeyValuePair(kvp)
aakvp = factory.ArrayOfArrayOfKeyValuePair(akvp)

# creds = factory.Credentials(Name=username, Password=password)

# ValueItem class description
# • "Hvt"–HistoryValueType– type of value (Double, Blob, String, Int64,
# NotDefined, ISODateTime, Boolean)
# • "Ivl"–Interval – interval in which the value was saved
# • "Ts"–UtcTimeStamp – time at which the value was valid
# • "Gt" – GoodThrough – time by which the value is valid
# • "Bv" – BooleanValue
# • "Dv" – DoubleValue
# • "Iv" - Int64Value
# • "Sv" – StringValue
# • "BinV" – BlobValue
# • "Dtv" - DateTimeValue

res = client.service.GetData(
    credentials=creds,
    variablesKey=aakvp,
    utcFrom='2020-01-08T10:00:00Z',
    utcTo='2020-01-08T12:00:00Z',
    variableOffset=0,
    variableCount=1,
    valueOffset=0,
    valueCount=10,
)

print(res)


def extract_variables():
    offset = 0
    count = 500
    keys = [
        "ClientId",
        "DPGuid",
        "DPName",
        "GroupName",
        "HistoryType",
        "StationName",
        "TechDPName"
    ]
    variables = []
    while True:
        res = client.service.GetAllVariables(credentials=creds, offset=offset, count=count)

        for vardesc in res['GetAllVariablesResult']['VariableDescription']:
            try:
                var = {kvp['Key']: kvp['Value'] for kvp in vardesc['Keys']['KeyValuePair'] if kvp['Key'] in keys}
                if var: # not an empty dict
                    variables.append(var)
            except Exception as e:
                print(e)
        if not res['moreDataAvailable']:
            break
        print(offset) # some status
        offset += count

                # try:
                #     print(f"{kvp['IsKey']:1} {kvp['Key']:20s} {kvp['Value']:30s}")
                # except:
                #     pass

    print("read:", len(variables))

    with open('variables.csv', 'w', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(variables)
