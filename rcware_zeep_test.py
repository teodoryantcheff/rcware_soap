import csv
import time
from datetime import datetime

import zeep

from credentials import username, password

# logging.basicConfig(level=logging.DEBUG)

wsdl = 'wsdl/RcWareDbAccess.wsdl'
settings = zeep.Settings(strict=True, xml_huge_tree=True, force_https=False, raw_response=False)

# Available ports are HistoryAccess, HistoryAccessGZip, HistoryAccess1. Only HistoryAccess seems to be alive.
client = zeep.Client(wsdl=wsdl, settings=settings, port_name='HistoryAccess')

print('Alive:', client.service.ServerAlive())

# AddMetadata(ns1: Credentials; credentials, ns1: ArrayOfMetadataRecord; records)
# CheckCredentials(ns1: Credentials; credentials)
# DeleteMetadata(ns1: Credentials; credentials, ns3: ArrayOfint; recordIds)
# GetAllVariables(ns1: Credentials; credentials, xs: int; offset, xs: int; count)
# GetData(ns1: Credentials; credentials, ns1: ArrayOfArrayOfKeyValuePair; variablesKey, xs: dateTime; utcFrom, xs: dateTime; utcTo, xs: int; variableOffset, xs: int; variableCount, xs: int; valueOffset, xs: int; valueCount)
# GetMetadata(ns1: Credentials; credentials, ns1: ArrayOfMetadataKeyValueItem; recordSpecifications, ns1: MetadataValueMatch; valueMatch, xs: int; offset, xs: int; count)
# GetParticularData(ns1: Credentials; credentials, ns1: ArrayOfArrayOfKeyValuePair; variableKeys, xs: dateTime; referenceTime, ns1: ParticularDataSpecification; dataSpecification, xs: int; variableOffset, xs: int; variableCount) GetVariables(ns1: Credentials; credentials, ns1: ArrayOfArrayOfKeyValuePair; variableKeys, xs: int; offset, xs: int; count)
# SaveData(ns1: Credentials; credentials, ns1: ArrayOfValueRecord; records)
# ServerAlive()
# UpdateMetadata(ns1: Credentials; credentials, ns1: ArrayOfMetadataRecord; records)

creds = {
    'Name': username,
    'Password': password
}
# creds = factory.Credentials(Name=username, Password=password)
print('Check Creds:', client.service.CheckCredentials(creds))
# print('Check Creds:', client.service.CheckCredentials(Name=username, Password=password))


factory = client.type_factory('http://schemas.datacontract.org/2004/07/ESG.Db.Server.Shared')

# kvp = factory.KeyValuePair(IsKey=True, Key='DPGuid', Value='C4C1EDF3-BACD-4552-9323-92E57D326907')
# kvp = factory.KeyValuePair(**{
#     'IsKey': True,
#     'Key': 'DPGuid',
#     'Value': 'C4C1EDF3-BACD-4552-9323-92E57D326907'
# })

# ac_power_kvp = factory.KeyValuePair(Key='DPGuid', Value='5175E60D-C94A-45CE-9F9D-E8F3E5A00C8D')  # AC_power
ac_power_kvp = factory.KeyValuePair(**{
    'Key': 'DPGuid',
    'Value': '5175E60D-C94A-45CE-9F9D-E8F3E5A00C8D'
})  # AC_power

dc_power_kvp = factory.KeyValuePair(Key='DPGuid', Value='C4C1EDF3-BACD-4552-9323-92E57D326907')  # DC_power
plant_malevo_kvp = factory.KeyValuePair(Key='StationName', Value='FVE_MALEVO')
plant_panchevo_kvp = factory.KeyValuePair(Key='StationName', Value='FVE_PANCHEVO')

ac_malevo_kvp = factory.ArrayOfKeyValuePair([ac_power_kvp, plant_malevo_kvp])
ac_panchevo_kvp = factory.ArrayOfKeyValuePair([ac_power_kvp, plant_panchevo_kvp])

dc_malevo_kvp = factory.ArrayOfKeyValuePair([dc_power_kvp, plant_malevo_kvp])
dc_panchevo_kvp = factory.ArrayOfKeyValuePair([dc_power_kvp, plant_panchevo_kvp])

# akvp2 = factory.ArrayOfKeyValuePair(kvp_ac)
aakvp = factory.ArrayOfArrayOfKeyValuePair([
    ac_malevo_kvp,
    ac_panchevo_kvp,
    dc_malevo_kvp,
    dc_panchevo_kvp
])

# print(aakvp)

start = time.time()
var_offset = 0
while True:
    res = client.service.GetData(
        credentials=creds,
        variablesKey=aakvp,
        # variablesKey=factory.ArrayOfArrayOfKeyValuePair(factory.ArrayOfKeyValuePair(factory.KeyValuePair(**kkk))),
        utcFrom='2020-05-11T08:00:00Z',
        # utcTo='2020-01-10T12:00:00Z',
        utcTo=datetime.utcnow(),
        variableOffset=var_offset,
        variableCount=4,
        valueOffset=0,
        valueCount=3000,
    )

    if res['returnCode'] != "0;OK;":
        exit(res['returnCode'])

    # print(res)

    # ValueItem class description
    # • "Hvt" – HistoryValueType– type of value (Double, Blob, String, Int64, NotDefined, ISODateTime, Boolean)
    # • "Ivl" – Interval – interval in which the value was saved
    # • "Ts" – UtcTimeStamp – time at which the value was valid
    # • "Gt" – GoodThrough – time by which the value is valid
    # • "Bv" – BooleanValue
    # • "Dv" – DoubleValue
    # • "Iv" - Int64Value
    # • "Sv" – StringValue
    # • "BinV" – BlobValue
    # • "Dtv" - DateTimeValue

    for mvr in res['GetDataResult']['Mvr']:
        print([k['Value'] for k in mvr['Keys']['KeyValuePair'] if k['Key'] in ['DPName', 'StationName']])
        for v in mvr['Vals']['I']:
            print(f"{v['Gt'].strftime('%Y-%m-%d %H:%M:%S.%f %Z')} {v['Dv']:7} ")
        print('--')

    var_offset = res['nextVariableOffset']
    if var_offset == -1:
        break

print("done in ", time.time() - start)

def extract_variables():
    offset = 0
    count = 2000
    keys = ("ClientId", "DPGuid", "DPName", "GroupName", "HistoryType", "StationName", "TechDPName")
    variables = []
    while True:
        r = client.service.GetAllVariables(credentials=creds, offset=offset, count=count)
        if r['GetAllVariablesResult'] is None or 'GetAllVariablesResult' not in r:
            print(r)
            break

        for vardesc in r['GetAllVariablesResult']['VariableDescription']:
            try:
                var = {kvp['Key']: kvp['Value'] for kvp in vardesc['Keys']['KeyValuePair'] if kvp['Key'] in keys}
                if var:  # not an empty dict
                    variables.append(var)
            except Exception as e:
                print(e)

        print(len(variables))  # some status

        if not r['moreDataAvailable']:
            break

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


# start = time.time()
# extract_variables()
# print("done in ", time.time() - start)
