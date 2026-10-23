<?php
declare(strict_types=1);
namespace Annam;
final class Content {
    public array $copy;public array $images;public array $design;public array $sections;
    public function __construct(public readonly Store $store){
        $defaults=json_decode(file_get_contents(ANNAM_ROOT.'/resources/storefront.json'),true,64,JSON_THROW_ON_ERROR);$this->copy=$defaults['copy'];$profile=$store->db->one('SELECT address,fssai_no FROM tenancy_billingprofile WHERE tenant_id=?',[$store->id()])??[];
        $this->copy=array_replace($this->copy,['brand.name'=>$store->name(),'footer.description'=>$store->config['tagline'],'footer.phone'=>$store->config['support_phone'],'footer.whatsapp'=>$store->config['support_phone'],'footer.email'=>$store->config['theme']['contact_email']??'','footer.address'=>$profile['address']??'','footer.fssai'=>$profile['fssai_no']??'']);
        foreach($store->config['home_sections'] as $section){$kind=$section['kind']??'';if(in_array($kind,['hero','spotlight'],true))foreach(['kicker','title','body','cta','points'] as $field)if(isset($section[$field]))$this->copy[$kind.'.'.$field]=is_array($section[$field])?implode("\n",$section[$field]):(string)$section[$field];}
        if(!$this->copy['hero.kicker']&&$store->config['tagline'])$this->copy['hero.kicker']=$store->config['tagline'];$this->design=$store->config['storefront_design']['published']??[];
        foreach($this->design['content']??[] as $key=>$value)if(is_string($value)&&array_key_exists($key,$this->copy))$this->copy[$key]=$value;
        $this->images=[];foreach($this->design['images']??[] as $key=>$url)if(is_string($url)&&preg_match('~^/platform/assets/'.preg_quote($store->tenant['slug'],'~').'/[a-f0-9-]{36}/$~D',$url))$this->images[$key]=$url;
        $this->sections=[];foreach($this->design['sections']??array_map(fn($key)=>['key'=>$key,'enabled'=>true],$defaults['sections']) as $section)if(($section['enabled']??false)&&in_array($section['key']??'',$defaults['sections'],true))$this->sections[]=$section['key'];
    }
    public function text(string $key): string {return e($this->copy[$key]??'');}
    public function image(string $key,string $fallback=''): string {return $this->images[$key]??image_url($fallback);}
    public function whatsapp(): string {$phone=preg_replace('/\D/','',$this->copy['footer.whatsapp']);if(strlen($phone)===10)$phone='91'.$phone;return preg_match('/^[0-9]{11,15}$/D',$phone)?'https://wa.me/'.$phone:'';}
    public static function link(string $value): string {
        $value=trim($value);if(!$value||preg_match('/[\x00-\x20\\\\]/',$value)||str_starts_with($value,'//'))return '';
        if(str_starts_with($value,'/')&&!str_starts_with($value,'//'))return $value;
        return filter_var($value,FILTER_VALIDATE_URL)&&in_array(strtolower(parse_url($value,PHP_URL_SCHEME)??''),['https','http'],true)?$value:'';
    }
    public function css(): string {
        $out='';foreach(['brand','paper','ink','surface_alt'] as $key){$value=$this->design['colors'][$key]??$this->store->config['theme'][$key]??'';if(preg_match('/^#[A-Fa-f0-9]{6}$/D',$value))$out.='--'.str_replace('_','-',$key).':'.$value.';';}return $out;
    }
}
