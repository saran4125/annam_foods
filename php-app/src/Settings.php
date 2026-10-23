<?php
declare(strict_types=1);
namespace Annam;

final class Settings {
    public function __construct(private Store $store) {}
    public static function owner(array $user): void {
        if (!$user['is_superuser'] && ($user['role']??'')!=='owner') throw new HttpError(403,'Only the store owner can change financial or integration settings.');
    }
    public static function validateCheckout(array $data): void {
        $pins=$data['courier_pincodes']??[];
        if(!is_array($pins)||count($pins)>10000)throw new HttpError(422,'Enter approved six-digit pincodes.');
        foreach($pins as $pin)if(!is_string($pin)||!preg_match('/^[1-9][0-9]{5}$/D',$pin))throw new HttpError(422,'Every pincode must contain six digits.');
        if(!is_bool($data['courier_enabled']??false))throw new HttpError(422,'Choose whether courier delivery is enabled.');
        if(($data['courier_enabled']??false)&&(!$pins||!isset($data['courier_fee'],$data['courier_minimum'])))throw new HttpError(422,'Set approved pincodes, charge and minimum before enabling courier delivery.');
        foreach(['courier_fee','courier_minimum'] as $key){try{$amount=Money::parse((string)($data[$key]??'0'));}catch(\InvalidArgumentException){throw new HttpError(422,'Enter valid courier amounts.');}if($amount>9999999)throw new HttpError(422,'Courier amounts cannot exceed ₹99,999.99.');}
        $dates=$data['closed_dates']??[];if(!is_array($dates)||count($dates)>366)throw new HttpError(422,'Enter at most 366 closed dates.');foreach($dates as $date)Store::date((string)$date);
        if(!is_string($data['payment_instructions']??'')||mb_strlen($data['payment_instructions']??'')>1000)throw new HttpError(422,'Payment instructions must be at most 1,000 characters.');
    }
    public function checkout(array $input): void {
        $pins=$input['pincodes']??[];if(!is_array($pins))throw new HttpError(422,'Use the pincode table.');
        $pins=array_values(array_unique(array_filter(array_map(fn($p)=>is_string($p)?trim($p):'', $pins),fn($p)=>$p!=='')));sort($pins);
        $data=['courier_enabled'=>!empty($input['courier_enabled']),'courier_pincodes'=>$pins,'courier_fee'=>(string)($input['courier_fee']??''),'courier_minimum'=>(string)($input['courier_minimum']??''),'closed_dates'=>preg_split('/\s+/',trim((string)($input['closed_dates']??'')),-1,PREG_SPLIT_NO_EMPTY),'payment_instructions'=>trim((string)($input['payment_instructions']??''))];
        self::validateCheckout($data);
        $this->store->db->transaction(function()use($data){$this->store->lock();$this->store->db->rows('UPDATE tenancy_tenantconfig SET checkout_settings=? WHERE tenant_id=?',[json_encode($data,JSON_THROW_ON_ERROR),$this->store->id()]);});$this->store->reload();
    }
    public function identity(array $input,array $files): void {
        $this->store->db->transaction(function()use($input,$files){
            $this->store->lock();$this->store->reload();$config=$this->store->config;$theme=$config['theme'];$features=$config['features'];$sections=$config['home_sections'];$design=$config['storefront_design'];$copy=$design['published']['content']??[];
            $strings=[];foreach(['brand_name'=>120,'tagline'=>200,'support_phone'=>20,'contact_email'=>254,'hero_kicker'=>100,'hero_title'=>160,'hero_body'=>600,'footer_address'=>600] as $key=>$limit){$value=trim((string)($input[$key]??''));if(mb_strlen($value)>$limit)throw new HttpError(422,'Check '.$key.'.');$strings[$key]=$value;}
            if(!$strings['brand_name'])throw new HttpError(422,'Enter the store name.');if($strings['contact_email']&&!filter_var($strings['contact_email'],FILTER_VALIDATE_EMAIL))throw new HttpError(422,'Enter a valid contact email.');
            $color=(string)($input['brand_color']??'');if(!preg_match('/^#[a-fA-F0-9]{6}$/D',$color))throw new HttpError(422,'Choose a valid brand colour.');
            $theme['brand']=$color;$theme['contact_email']=$strings['contact_email'];$theme['announcements']=array_slice(preg_split('/\r?\n/',trim((string)($input['announcements']??'')),-1,PREG_SPLIT_NO_EMPTY),0,8);
            if(($files['logo']['error']??UPLOAD_ERR_NO_FILE)!==UPLOAD_ERR_NO_FILE){$theme['logo_url']='/media/'.Resources::upload($files['logo'],'brand');unset($design['published']['images']['logo']);}
            foreach(['website_ordering','snacks_courier','manual_payments','cod'] as $key)$features[$key]=!empty($input[$key]);
            $sections=array_values(array_filter($sections,fn($s)=>($s['kind']??'')!=='hero'));$sections[]=['kind'=>'hero','kicker'=>$strings['hero_kicker'],'title'=>$strings['hero_title'],'body'=>$strings['hero_body']];
            foreach(['brand.name'=>'brand_name','hero.kicker'=>'hero_kicker','hero.title'=>'hero_title','hero.body'=>'hero_body','footer.description'=>'tagline','footer.phone'=>'support_phone','footer.whatsapp'=>'support_phone','footer.email'=>'contact_email','footer.address'=>'footer_address'] as $key=>$source)$copy[$key]=$strings[$source];
            $design['published']['content']=$copy;$design['published']['colors']['brand']=$color;
            $this->store->db->rows('UPDATE tenancy_tenantconfig SET brand_name=?,tagline=?,support_phone=?,theme=?,features=?,home_sections=?,storefront_design=? WHERE tenant_id=?',[$strings['brand_name'],$strings['tagline'],$strings['support_phone'],json_encode($theme,JSON_THROW_ON_ERROR),json_encode($features,JSON_THROW_ON_ERROR),json_encode($sections,JSON_THROW_ON_ERROR),json_encode($design,JSON_THROW_ON_ERROR),$this->store->id()]);
        });$this->store->reload();
    }
    public static function validateProfile(array $profile): void {
        foreach(['legal_name','address','state','state_code','fssai_no','invoice_prefix','number_format'] as $field)if(!trim((string)($profile[$field]??'')))throw new HttpError(422,'Complete the billing '.$field.'.');
        if(!preg_match('/^[0-9]{14}$/D',$profile['fssai_no'])||!preg_match('/^[0-9]{2}$/D',$profile['state_code']))throw new HttpError(422,'Check the FSSAI licence and state code.');
        if(!in_array($profile['gst_mode'],['regular','composition','unregistered'],true)||!in_array($profile['bill_timing'],['on_payment','on_delivery'],true))throw new HttpError(422,'Choose valid tax and bill timing settings.');
        if($profile['gst_mode']!=='unregistered'&&(!preg_match('/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/D',$profile['gstin'])||substr($profile['gstin'],0,2)!==$profile['state_code']))throw new HttpError(422,'Enter the registered GSTIN matching the seller state.');
        try{$rate=Money::parse((string)$profile['tax_rate']);}catch(\InvalidArgumentException){throw new HttpError(422,'Enter a valid tax rate.');}if($rate>10000)throw new HttpError(422,'Tax rate cannot exceed 100%.');
        self::number($profile['number_format'],$profile['invoice_prefix'],'26-27',1);
    }
    public static function number(string $format,string $prefix,string $fy,int $sequence): string {
        $number=str_replace(['{prefix}','{fy}'],[$prefix,$fy],$format);
        $number=preg_replace_callback('/\{seq(?::0?([1-9])d)?\}/',fn($m)=>str_pad((string)$sequence,(int)($m[1]??0),'0',STR_PAD_LEFT),$number);
        if(!preg_match('/^[A-Za-z0-9\/-]{1,16}$/D',$number)||!str_contains($format,'{seq'))throw new HttpError(422,'Bill format must include {seq:05d} and produce at most 16 letters, digits, slashes or hyphens.');return $number;
    }
    public function profile(array $input): void {
        $data=$this->store->profile();
        foreach(['legal_name'=>160,'address'=>2000,'state'=>80,'state_code'=>2,'gstin'=>15,'fssai_no'=>14,'invoice_prefix'=>10,'number_format'=>80,'gst_mode'=>20,'bill_timing'=>20,'tax_rate'=>10,'sac'=>12,'footer'=>2000] as $key=>$limit){$value=trim((string)($input[$key]??''));if(mb_strlen($value)>$limit)throw new HttpError(422,'Billing field '.$key.' is too long.');$data[$key]=$value;}
        foreach(['prices_include_tax','round_total','delivery_fee_taxable'] as $key)$data[$key]=!empty($input[$key]);self::validateProfile($data);
        $keys=['legal_name','address','state','state_code','gstin','fssai_no','invoice_prefix','number_format','gst_mode','bill_timing','tax_rate','sac','footer','prices_include_tax','round_total','delivery_fee_taxable'];
        $this->store->db->transaction(function()use($data,$keys){$this->store->lock();$this->store->db->rows('UPDATE tenancy_billingprofile SET '.implode(',',array_map(fn($k)=>$k.'=?',$keys)).' WHERE tenant_id=?',[...array_map(fn($k)=>$data[$k],$keys),$this->store->id()]);});
    }
}
