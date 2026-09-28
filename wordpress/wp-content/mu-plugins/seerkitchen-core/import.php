<?php
defined('ABSPATH') || exit;
/** Read-only source extraction is separate from this site-scoped importer. */
function seer_import_normalize(array $snapshot): array {
    $snapshot['image']=(int)($snapshot['image']??0);
    $snapshot['categories']=array_map('intval',$snapshot['categories']??[]);sort($snapshot['categories']);
    foreach($snapshot['variations']??[] as $id=>$v)$snapshot['variations'][$id][3]=(int)$v[3];
    return $snapshot;
}
function seer_import_snapshot(WC_Product $p): array {
    $out = ['name'=>$p->get_name('edit'),'slug'=>$p->get_slug('edit'),'description'=>$p->get_description('edit'),
        'short_description'=>$p->get_short_description('edit'),'status'=>$p->get_status('edit'),
        'regular_price'=>$p->get_regular_price('edit'),'sale_price'=>$p->get_sale_price('edit'),
        'stock_status'=>$p->get_stock_status('edit'),'categories'=>$p->get_category_ids(),
        'image'=>(int)$p->get_image_id(),'gallery'=>$p->get_gallery_image_ids(),'kind'=>$p->get_meta('_seer_fulfilment'),
        'attributes'=>array_map(fn($a)=>$a->get_data(),$p->get_attributes())];
    if ($p->is_type('variable')) {
        $out['variations']=[];
        foreach($p->get_children() as $id) {
            $v=wc_get_product($id);
            $out['variations'][$id]=[$v->get_attributes(),$v->get_regular_price('edit'),$v->get_stock_status('edit'),(int)$v->get_image_id()];
        }
    }
    return seer_import_normalize($out);
}
function seer_import_media(string $url, array $manifest, string $alt = ''): int {
    $existing=get_posts(['post_type'=>'attachment','post_status'=>'inherit','fields'=>'ids','numberposts'=>2,
        'meta_key'=>'_seer_source_url','meta_value'=>$url]);
    if(count($existing)>1) throw new RuntimeException('Duplicate media source: '.$url);
    if($existing) {
        $id=(int)$existing[0];
        $current=get_post_meta($id,'_wp_attachment_image_alt',true);
        $seeded=get_post_meta($id,'_seer_seeded_alt',true);
        $filename_alt=sanitize_text_field(pathinfo(basename(parse_url($url,PHP_URL_PATH)),PATHINFO_FILENAME));
        if($alt && (!$current || $current===$filename_alt || ($seeded && $current===$seeded))) {
            $readable=sanitize_text_field($alt);
            update_post_meta($id,'_wp_attachment_image_alt',$readable);
            update_post_meta($id,'_seer_seeded_alt',$readable);
        }
        return $id;
    }
    $filename=$manifest['assets'][$url]??'';
    if(!$filename || basename($filename)!==$filename) throw new RuntimeException('Missing downloaded image: '.$url);
    $path='/opt/seer/data/assets/'.$filename;
    if(!is_file($path))$path='/opt/seer/data/artwork/'.$filename;
    if(!is_file($path)) throw new RuntimeException('Missing image file: '.$filename);
    require_once ABSPATH.'wp-admin/includes/file.php';
    require_once ABSPATH.'wp-admin/includes/media.php';
    require_once ABSPATH.'wp-admin/includes/image.php';
    $temp=wp_tempnam($filename);
    if(!copy($path,$temp)) throw new RuntimeException('Cannot copy image.');
    $id=media_handle_sideload(['name'=>$filename,'tmp_name'=>$temp],0);
    if(is_wp_error($id)){@unlink($temp);throw new RuntimeException($id->get_error_message());}
    update_post_meta($id,'_seer_source_url',$url);
    $readable=sanitize_text_field($alt?:pathinfo(basename(parse_url($url,PHP_URL_PATH)),PATHINFO_FILENAME));
    update_post_meta($id,'_wp_attachment_image_alt',$readable);
    update_post_meta($id,'_seer_seeded_alt',$readable);
    return (int)$id;
}
function seer_import_find(string $url): array {
    return get_posts(['post_type'=>['product','page','seer_campaign'],'post_status'=>'any','fields'=>'ids','numberposts'=>3,
        'meta_key'=>'_seer_source_url','meta_value'=>$url]);
}
function seer_import_variant_plan(array $row): array {
    $values=$row['variant_values']??[];
    if(!$row['variants']) return [];
    if(!$values) throw new RuntimeException('Variant labels and prices are missing.');
    $index=[];
    foreach($values as $name=>$options) foreach($options as $option) $index[$option['code']]=['name'=>$name,'option'=>$option];
    $result=[];
    foreach($row['variants'] as $combination) {
        $attrs=[];$prices=[];
        foreach($combination['variants'] as $code) {
            if(!isset($index[$code])) throw new RuntimeException('Unknown option code '.$code);
            $data=$index[$code];$attrs[$data['name']]=(string)$data['option']['name'];
            if(($data['option']['priceType']??'fixed')!=='fixed') throw new RuntimeException('Unsupported option pricing.');
            $prices[]=Seer_Kitchen::money((string)($data['option']['sellingPrice']??''));
        }
        // Multiple independently priced dimensions need explicit interpretation.
        if(count(array_unique($prices))!==1) throw new RuntimeException('Ambiguous combination price.');
        $result[]=['attributes'=>$attrs,'price'=>$prices[0],'available'=>!empty($combination['available'])];
    }
    return $result;
}
if(defined('WP_CLI') && WP_CLI) {
    WP_CLI::add_command('seer import',function($args,$assoc){
        if(get_current_blog_id()===get_main_site_id()) WP_CLI::error('Select a kitchen using --url.');
        $file=$args[0]??'/opt/seer/data/catalog.json';
        $m=json_decode(file_get_contents($file),true,512,JSON_THROW_ON_ERROR);
        if(rtrim($m['source']??'','/')!=='https://www.annamfood.in') WP_CLI::error('Unrecognised source manifest.');
        $plan=[];$counts=['create'=>0,'update'=>0,'unchanged'=>0,'owner_conflict'=>0,'duplicate'=>0];
        foreach($m['products'] as $row){
            $ids=seer_import_find($row['source_url']);$action='create';$id=$ids[0]??0;
            $reasons=$row['review_reasons'];$variants=[];
            try{$variants=seer_import_variant_plan($row);}catch(Throwable $e){$reasons[]=$e->getMessage();}
            if(empty($row['images'])) $reasons[]='Product photograph missing.';
            foreach($row['images'] as $image) if(empty($m['assets'][$image])) $reasons[]='Image download missing.';
            $fingerprint=hash('sha256',wp_json_encode($row));
            if(count($ids)>1)$action='duplicate';
            elseif($id){
                $p=wc_get_product($id);
                $stored=get_post_meta($id,'_seer_import_snapshot',true);
                if(!$p || !is_array($stored) || seer_import_snapshot($p)!==seer_import_normalize($stored))$action='owner_conflict';
                elseif(get_post_meta($id,'_seer_source_hash',true)===$fingerprint && $p->get_status()===($reasons?'draft':'publish'))$action='unchanged';
                else $action='update';
            }
            $counts[$action]++;
            $plan[]=['source_url'=>$row['source_url'],'source_id'=>$row['source_id'],'id'=>$id,'action'=>$action,
                'hash'=>$fingerprint,'status'=>$reasons?'draft':'publish','price'=>$row['price'],'review_reasons'=>array_values(array_unique($reasons)),
                'variants'=>$variants,'current'=>$id&&isset($p)&&$p?seer_import_snapshot($p):null];
            unset($p);
        }
        $digest=hash('sha256',wp_json_encode([$m['categories'],$plan,$m['pages']]));
        $report=['site'=>home_url('/'),'source'=>$m['source'],'fetched_at'=>$m['fetched_at'],'plan_digest'=>$digest,
            'counts'=>$counts,'source_failures'=>$m['failures'],'products'=>$plan,'pages'=>'Imported as review drafts; stale template marketing excluded.'];
        $report_path=$assoc['report']??'/opt/seer/reports/annam-import-plan.json';
        $approved=false;
        if(isset($assoc['approve-report'])){
            $review=json_decode(file_get_contents($assoc['approve-report']),true,512,JSON_THROW_ON_ERROR);
            if(($review['plan_digest']??'')!==$digest || ($review['site']??'')!==home_url('/'))WP_CLI::error('The approved report is stale or belongs to another site. Run a fresh dry run.');
            $approved=true;
        }
        file_put_contents($report_path,wp_json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
        WP_CLI::log(wp_json_encode($counts));
        if(!isset($assoc['apply'])){WP_CLI::success('Dry run written to '.$report_path);return;}
        if($counts['duplicate'])WP_CLI::error('Duplicate source identities must be reconciled before applying.');
        $categories=[];$source_ids=[];
        foreach($m['categories'] as $row){
            $term=get_term_by('slug',$row['slug'],'product_cat');
            if(!$term){$created=wp_insert_term($row['name'],'product_cat',['slug'=>$row['slug'],'description'=>wp_kses_post($row['description'])]);if(is_wp_error($created))throw new RuntimeException($created->get_error_message());$id=(int)$created['term_id'];}
            else $id=$term->term_id;
            $categories[$row['slug']]=$id;$source_ids[$row['source_id']]=$id;
            if(!get_term_meta($id,'_seer_source_url',true)){
                update_term_meta($id,'_seer_source_url',$row['source_url']);
                if($row['image'] && isset($m['assets'][$row['image']]))update_term_meta($id,'thumbnail_id',seer_import_media($row['image'],$m,$row['name']));
            }
        }
        foreach($m['categories'] as $row)if(isset($source_ids[$row['parent_id']])&&!get_term_meta($categories[$row['slug']],'_seer_parent_seeded',true)){
            wp_update_term($categories[$row['slug']],'product_cat',['parent'=>$source_ids[$row['parent_id']]]);
            update_term_meta($categories[$row['slug']],'_seer_parent_seeded',1);
        }
        $applied=0;
        foreach($m['products'] as $i=>$row){
            $change=$plan[$i];
            if($change['action']==='unchanged'||($change['action']==='owner_conflict'&&!$approved))continue;
            $variable=(bool)$change['variants'];
            $p=$change['id']?wc_get_product($change['id']):($variable?new WC_Product_Variable():new WC_Product_Simple());
            if($variable!==$p->is_type('variable')){WP_CLI::warning('Product type changed; review manually: '.$row['slug']);continue;}
            $p->set_name($row['name']);$p->set_slug($row['slug']);$p->set_description(wp_kses_post($row['description']));
            $p->set_short_description(wp_kses_post($row['short_description']));$p->set_status($change['status']);
            $p->set_category_ids(array_values(array_filter(array_map(fn($slug)=>$categories[$slug]??0,$row['categories']))));
            $p->set_stock_status($row['available']?'instock':'outofstock');$p->set_manage_stock(false);
            $p->update_meta_data('_seer_fulfilment',$row['fulfilment']);$p->update_meta_data('_seer_source_url',$row['source_url']);
            $p->update_meta_data('_seer_source_id',$row['source_id']);$p->update_meta_data('_seer_review_reasons',$change['review_reasons']);
            $photos=[];foreach($row['images'] as $url)if(isset($m['assets'][$url]))$photos[]=seer_import_media($url,$m,$row['name']);
            $p->set_image_id($photos[0]??0);$p->set_gallery_image_ids(array_slice($photos,1));
            if(!$variable){$p->set_regular_price($row['price']??'');$p->set_sale_price('');}
            else {
                $options=[];foreach($change['variants'] as $v)foreach($v['attributes'] as $name=>$value)$options[$name][]=$value;
                $attributes=[];foreach($options as $name=>$values){$a=new WC_Product_Attribute();$a->set_name($name);$a->set_options(array_values(array_unique($values)));$a->set_visible(true);$a->set_variation(true);$attributes[]=$a;}
                $p->set_attributes($attributes);
            }
            $id=$p->save();
            if($variable){
                $old=[];foreach($p->get_children() as $vid){$v=wc_get_product($vid);$old[hash('sha256',wp_json_encode($v->get_attributes()))]=$v;}
                $keep=[];
                foreach($change['variants'] as $v){
                    $attrs=[];foreach($v['attributes'] as $name=>$value)$attrs[sanitize_title($name)]=$value;
                    $key=hash('sha256',wp_json_encode($attrs));$variation=$old[$key]??new WC_Product_Variation();
                    $variation->set_parent_id($id);$variation->set_attributes($attrs);$variation->set_regular_price($v['price']);$variation->set_sale_price('');
                    $variation->set_stock_status($row['available']&&$v['available']?'instock':'outofstock');$variation->set_image_id($photos[0]??0);$keep[]=$variation->save();
                }
                foreach($old as $v)if(!in_array($v->get_id(),$keep,true))$v->delete(true);
                WC_Product_Variable::sync($id);wc_delete_product_transients($id);$p=wc_get_product($id);
            }
            update_post_meta($id,'_seer_source_hash',$change['hash']);
            update_post_meta($id,'_seer_import_snapshot',seer_import_snapshot($p));
            $applied++;
            if($applied%25===0)WP_CLI::log('Imported '.$applied.' products…');
        }
        foreach($m['pages'] as $page){
            if(seer_import_find($page['source_url'])||get_page_by_path($page['slug']))continue;
            $source=$page['source_page']['page']??[];$html='';
            foreach($source['components']??[] as $component){
                if(in_array($component['componentType'],['Header','Footer','Team','Product Card','App Store','address Book List'],true))continue;
                $walk=function($data)use(&$walk,&$html){if(!is_array($data))return;foreach($data as $key=>$value){if($key==='text'&&is_string($value)&&trim(wp_strip_all_tags($value)))$html.=wp_kses_post($value)."\n";elseif(is_array($value))$walk($value);}};
                $walk($component['data']??[]);
            }
            $id=wp_insert_post(['post_type'=>'page','post_status'=>'draft','post_name'=>$page['slug'],'post_title'=>$source['name']??ucwords($page['slug']),'post_content'=>$html]);
            update_post_meta($id,'_seer_source_url',$page['source_url']);update_post_meta($id,'_seer_review_reasons',['Confirm policy, delivery scope and accuracy before publishing.']);
        }
        foreach($m['campaigns']??[] as$campaign){
            $identity=$campaign['source_url'].'#campaign-'.hash('sha256',$campaign['image']);
            if(seer_import_find($identity)||!isset($m['assets'][$campaign['image']]))continue;
            $image=seer_import_media($campaign['image'],$m);
            $id=wp_insert_post(['post_type'=>'seer_campaign','post_status'=>'draft','post_title'=>'Source artwork · review dates and claims','post_content'=>'<!-- wp:image {"id":'.$image.'} --><figure class="wp-block-image"><img src="'.esc_url(wp_get_attachment_url($image)).'" alt="Source campaign pending review"/></figure><!-- /wp:image -->']);
            update_post_meta($id,'_seer_source_url',$identity);update_post_meta($id,'_seer_review_reasons',[$campaign['reason']]);
        }
        update_option('seer_import_report',array_intersect_key($report,array_flip(['source','fetched_at','counts','source_failures'])));
        flush_rewrite_rules();
        WP_CLI::success('Applied '.$applied.' products. Owner conflicts were '.($approved?'explicitly approved.':'preserved.'));
    });
}
add_action('init',function(){register_post_type('seer_campaign',['label'=>'Campaign archive','public'=>false,'show_ui'=>true,'show_in_rest'=>true,'supports'=>['title','editor','thumbnail'],'capability_type'=>'page','map_meta_cap'=>true]);});
