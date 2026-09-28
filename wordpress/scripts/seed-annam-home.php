<?php
if(!defined('WP_CLI')||!WP_CLI||get_current_blog_id()!==2)throw new RuntimeException('Use the local Annam site.');
define('SEER_PROVISION_LIBRARY',true);require '/opt/seer/scripts/provision.php';
if(get_option('seer_storefront_seeded')){WP_CLI::success('Existing owner homepage preserved.');return;}
$m=json_decode(file_get_contents('/opt/seer/data/catalog.json'),true,512,JSON_THROW_ON_ERROR);
$hero=[];$promos=[];
foreach(['sweets'=>['sweets','tirunelveli-halwa','Explore sweets'],'savouries'=>['pakshanams-1','butter-murukku','Savour every crunch'],'pantry'=>['podi','pirandai-podi','Stock your pantry']]as$key=>$data){
    foreach(['hero-'.$key.'.png','mobile-'.$key.'.png']as$file){if(!is_file('/opt/seer/data/artwork/'.$file))throw new RuntimeException('Artwork missing: '.$file);$m['assets']['seer-artwork://'.$file]=$file;}
    $hero[]=['image'=>seer_import_media('seer-artwork://hero-'.$key.'.png',$m),'mobile'=>seer_import_media('seer-artwork://mobile-'.$key.'.png',$m),'alt'=>$data[2],'url'=>home_url('/categories/'.$data[0].'/')];
    $source=current(array_filter($m['products'],fn($p)=>$p['slug']===$data[1]));
    $promos[]=['image'=>seer_import_media($source['images'][0],$m),'alt'=>$data[2],'url'=>home_url('/categories/'.$data[0].'/')];
}
$hero=array_map(function($item){$item['imagePreview']=wp_get_attachment_url($item['image']);$item['mobilePreview']=wp_get_attachment_url($item['mobile']);return $item;},$hero);
$promos=array_map(function($item){$item['imagePreview']=wp_get_attachment_url($item['image']);return $item;},$promos);
$logo=seer_import_media($m['brand']['logo'],$m);set_theme_mod('custom_logo',$logo);update_option('site_logo',$logo);
$feature=['tirunelveli-halwa','butter-murukku','pirandai-podi','kalyana-mysore-pak','spl-mixture','lemon-pickle'];$featured=0;
foreach($feature as$slug){$post=get_page_by_path($slug,OBJECT,'product');if($post){$p=wc_get_product($post->ID);if($p->get_status()==='publish'){$p->set_featured(true);$p->save();$featured++;}}}
if($featured<6)foreach(wc_get_products(['status'=>'publish','limit'=>12,'orderby'=>'date','order'=>'ASC'])as$p){if(!$p->get_image_id()||$p->get_meta('_seer_fulfilment')!=='packaged_goods'||$p->get_featured())continue;$p->set_featured(true);$p->save();if(++$featured>=6)break;}
$story=wp_get_attachment_image_url($promos[2]['image'],'large');
wp_update_post(['ID'=>get_option('page_on_front'),'post_content'=>seer_home_blocks($hero,$promos,$story)]);
update_option('seer_phone','9551079550');update_option('seer_email','annamsfoods@gmail.com');
update_option('seer_notice','ANNAM FOODS · Sweets, savouries & everyday favourites');
update_option('blogdescription','Namma athu sappadu. A little taste of home.');
update_option('seer_storefront_seeded',1);wc_delete_product_transients();
WP_CLI::success('Seeded three desktop/mobile campaigns, three independent tiles, logo and photographed featured products.');
