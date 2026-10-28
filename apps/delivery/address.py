"""Place-of-supply codes from an explicitly provided delivery state/country."""
STATE_CODES = {
    'jammuandkashmir':'01','jammu&kashmir':'01','himachalpradesh':'02','punjab':'03','chandigarh':'04',
    'uttarakhand':'05','haryana':'06','delhi':'07','newdelhi':'07','rajasthan':'08','uttarpradesh':'09',
    'bihar':'10','sikkim':'11','arunachalpradesh':'12','nagaland':'13','manipur':'14','mizoram':'15',
    'tripura':'16','meghalaya':'17','assam':'18','westbengal':'19','jharkhand':'20','odisha':'21','orissa':'21',
    'chhattisgarh':'22','madhyapradesh':'23','gujarat':'24','damananddiu':'26',
    'dadraandnagarhaveli':'26','dadraandnagarhavelianddamananddiu':'26','maharashtra':'27',
    'karnataka':'29','goa':'30','lakshadweep':'31','kerala':'32','tamilnadu':'33','puducherry':'34',
    'pondicherry':'34','andamanandnicobarislands':'35','telangana':'36','andhrapradesh':'37','ladakh':'38',
}


def state_code(country,state):
    if (country or 'India').strip().casefold()!='india':
        return '96'
    key=''.join((state or '').casefold().split())
    return STATE_CODES.get(key,'')
