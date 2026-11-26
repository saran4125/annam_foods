<?php
declare(strict_types=1);
namespace Annam;

/** Adapters for features added to the reference after the initial PHP rebuild. */
final class ParityRoutes {
    public function __construct(private Store $store,private array $user,private \Closure $render){}
    private function view(string $view,array $data=[]):void {($this->render)($view,$data,true);}
    private function back(string $fallback):string {$url=$_POST['return_url']??$_GET['return_url']??$fallback;return is_string($url)&&str_starts_with($url,'/manage/')&&!str_contains($url,'\\')?$url:$fallback;}
    public function admin(string $path,string $method):bool {
        if(str_starts_with($path,'/manage/categories/')||str_starts_with($path,'/manage/dishes/'))(new Catalog($this->store))->defaults();
        if($path==='/manage/customer-lookup/'){if($method!=='GET')throw new HttpError(405,'GET required.');Operations::limit($this->store,'lookup:'.$this->user['id'],60,60);header('Content-Type: application/json');echo json_encode((new CustomerLookup($this->store))->find((string)($_GET['phone']??'')),JSON_THROW_ON_ERROR);return true;}
        if($path==='/manage/reports/'){$service=new Reports($this->store);$form_error='';try{$report=$service->data($_GET);}catch(HttpError $error){if($error->status!==422)throw $error;http_response_code(422);$form_error=$error->getMessage();$report=['rows'=>[],'start'=>(string)($_GET['start']??date('Y-m-d').'T00:00'),'end'=>(string)($_GET['end']??date('Y-m-d\TH:i')),'order_count'=>0,'quantity'=>0,'items_amount'=>'0'];}$sales=$service->sales();if(($_GET['export']??'')==='csv'&&!$form_error)Reports::csv($report);else $this->view('reports',compact('report','sales','form_error'));return true;}
        if($path==='/manage/orders/'){$result=(new Reports($this->store))->orderGroups($_GET);$this->view('orders',$result);return true;}
        if(preg_match('~^/manage/orders/(\d+)/courier/$~',$path,$m)){
            Settings::owner($this->user);if($method!=='POST')throw new HttpError(405,'POST required.');$service=new Courier($this->store);$actor=$this->user['username'];
            if(($_POST['action']??'')==='dispatch')$service->dispatch((int)$m[1],(string)($_POST['amount']??''),(string)($_POST['courier_name']??''),(string)($_POST['tracking_number']??''),$actor);
            elseif(($_POST['action']??'')==='paid'){if(empty($_POST['received']))throw new HttpError(422,'Confirm courier payment was received.');$service->confirm((int)$m[1],(string)($_POST['reference']??''),$actor);}else throw new HttpError(422,'Choose a valid courier action.');redirect('/manage/orders/'.$m[1].'/');
        }
        if($path==='/manage/courier-notices/release/'){Settings::owner($this->user);if($method!=='POST')throw new HttpError(405,'POST required.');if(($_POST['confirmed']??'')!=='yes')throw new HttpError(422,'Confirm that the customer and team templates have been approved.');$count=(new Courier($this->store))->release();$_SESSION['notice']=$count.' courier notices queued.';redirect('/manage/checkout-settings/');}
        if(preg_match('~^/manage/categories/(\d+)/delete/$~',$path,$m)){
            $resources=new Resources($this->store);$category=$resources->get('categories',(int)$m[1]);
            if($method==='POST'){
                if(($_POST['confirmed']??'')!=='yes')throw new HttpError(422,'Confirm category deletion.');
                $resources->deleteCategory((int)$category['id']);$_SESSION['notice']='Category deleted. Its dishes, products and subcategories were kept.';redirect('/manage/categories/?category_view=all');
            }
            $itemCount=(int)$this->store->db->one('SELECT COUNT(*) AS n FROM catalog_menuitem WHERE tenant_id=? AND category_id=?',[$this->store->id(),$category['id']])['n'];
            $childCount=(int)$this->store->db->one('SELECT COUNT(*) AS n FROM catalog_menucategory WHERE tenant_id=? AND parent_id=?',[$this->store->id(),$category['id']])['n'];
            $this->view('category-delete',compact('category','itemCount','childCount'));return true;
        }
        if($path==='/manage/categories/'){
            $categories=$this->categories();$scope=$_GET['category_view']??'main';$query=trim((string)($_GET['q']??''));$records=array_values(array_filter($categories,fn($c)=>(match($scope){'main'=>isset(Catalog::DEFAULTS[$c['slug']]),'custom'=>!isset(Catalog::DEFAULTS[$c['slug']]),'empty'=>$c['total']===0,'populated'=>$c['total']>0,default=>true})&&(!$query||mb_stripos($c['name'],$query)!==false)));$this->view('categories',compact('records','categories','scope','query'));return true;
        }
        $category=null;$base='/manage/dishes/';
        if(preg_match('~^/manage/categories/(\d+)/items/(.*)$~',$path,$m)){$category=(new Resources($this->store))->get('categories',(int)$m[1]);$base='/manage/categories/'.$category['id'].'/items/';$suffix=$m[2];}
        elseif(str_starts_with($path,$base))$suffix=substr($path,strlen($base));else return false;
        if($suffix==='menu/')return false;
        if(preg_match('~^(\d+)/quantity/$~',$suffix,$m)){
            $item=$this->store->item((int)$m[1]);$this->assertCategory($category,$item);$inventory=new Inventory($this->store);$slots=array_values(array_filter($this->store->slots(),fn($s)=>isset(Catalog::MEALS[$s['key']])));$meal=$item['fulfilment']==='scheduled';$date=$meal?Store::date((string)($_POST['date']??$_GET['date']??date('Y-m-d'))):null;
            $preferred=$category&&isset(Catalog::MEALS[$category['slug']])?$category['slug']:((new Catalog($this->store))->meals($item)[0]??'breakfast');$assigned=$this->store->db->one('SELECT id AS slot_id FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$preferred]);$slotId=$meal?(int)($_POST['slot_id']??$_GET['slot_id']??$assigned['slot_id']??$slots[0]['id']??0):null;if($meal)$this->store->slot($slotId);
            $return_url=$this->back($category?$base:'/manage/dishes/?kind='.$item['fulfilment']);$error='';$values=[];
            if($method==='POST'){try{$inventory->configure((int)$item['id'],$date,$slotId,!empty($_POST['track_quantity']),$_POST['quantity']??null,(string)($_POST['operation']??'set'),(int)($_POST['stock_revision']??-1));$_SESSION['notice']='Quantity tracking saved.';redirect($return_url);}catch(HttpError $e){if(!in_array($e->status,[409,422],true))throw $e;http_response_code($e->status);$error=$e->getMessage();if($e->status===422)$values=$_POST;}}
            $state=$inventory->state($item,$date,$slotId);$this->view('quantity',compact('item','meal','date','slotId','slots','return_url','state','error','values'));return true;
        }
        if(preg_match('~^(\d+)/(stock|toggle|archive)/$~',$suffix,$m)){
            if($method!=='POST')throw new HttpError(405,'Use the action form.');$item=$this->store->item((int)$m[1]);$this->assertCategory($category,$item);
            if($m[2]==='stock'){if(!in_array($_POST['enabled']??null,['0','1'],true))throw new HttpError(422,'Refresh the item list before changing stock.');$this->store->setItemFlag((int)$item['id'],'in_stock',$_POST['enabled']==='1');}
            elseif($m[2]==='toggle'&&!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],(int)$item['id'],!empty($_POST['available']),(int)$_POST['revision']);
            elseif($m[2]==='archive'&&!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],(int)$item['id'],false,(int)$_POST['revision']);
            elseif($m[2]==='archive')(new Resources($this->store))->removeFromSale('dishes',(int)$item['id']);else (new Resources($this->store))->toggle('dishes',(int)$item['id']);redirect($this->back($base));
        }
        if(preg_match('~^(new|\d+)/$~',$suffix,$m)){
            $key='dishes';$spec=Resources::definition($key);$id=$m[1]==='new'?null:(int)$m[1];$record=$id?$this->store->item($id):['active'=>true,'in_stock'=>true,'is_veg'=>true,'sort'=>0,'price'=>'0','fulfilment'=>$_GET['kind']??($category&&isset(Catalog::MEALS[$category['slug']])?'scheduled':'courier'),'category_id'=>$category['id']??null];if($id)$this->assertCategory($category,$record);$return_url=$this->back($base);$fixed_category_id=$category?($record['category_id']??$category['id']):null;
            if($method==='POST'){try{$input=$_POST;if($category)$input['category_id']=$fixed_category_id;$this->store->db->transaction(function()use($id,$input){$saved=(new Resources($this->store))->save('dishes',$id,$input,$_FILES);if(!empty($input['meals_present']))(new Catalog($this->store))->assign($saved,$input['meals']??[]);if(!empty($_POST['schedule_present'])&&empty($_POST['menu_date'])&&!empty($_POST['slot'])){if(!is_array($_POST['weekdays']??[]))throw new HttpError(422,'Choose valid weekdays.');$this->store->saveWeeklyMembership($saved,(int)$_POST['slot'],$_POST['weekdays']??[]);}if(!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],$saved,!empty($_POST['day_available']),(int)$_POST['day_revision']);});$_SESSION['notice']='Item saved.';redirect($return_url);}catch(HttpError|\InvalidArgumentException $error){if($error instanceof HttpError&&$error->status!==422)throw $error;$form_error=$error->getMessage();http_response_code(422);$record=array_replace($record,$_POST);}}
            $this->view('resource-edit',compact('key','spec','id','record','return_url','fixed_category_id')+['form_error'=>$form_error??'']);return true;
        }
        if($suffix!=='')return false;
        $kind=(string)($_GET['kind']??$_GET['type']??'scheduled');if(!in_array($kind,['scheduled','courier'],true))$kind='scheduled';if($category&&isset(Catalog::DEFAULTS[$category['slug']]))$kind=$category['slug']==='shop'?'courier':'scheduled';$meal=(string)($_GET['meal']??($kind==='scheduled'?'breakfast':''));$query=mb_substr(trim((string)($_GET['q']??'')),0,80);$date=($_GET['date']??'')==='all'?null:Store::date((string)($_GET['date']??date('Y-m-d')));$slot=null;$revision=0;if(!$category&&$kind==='scheduled'&&$meal==='')$meal='breakfast';
        if(!$category&&$kind==='scheduled'&&$meal&&$meal!=='unassigned')$slot=$this->store->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$meal]);
        $filters=[];foreach(['stock'=>'in_stock','status'=>'active'] as $param=>$field)if(isset($_GET[$param])&&in_array($_GET[$param],['0','1'],true))$filters[$field]=$_GET[$param]==='1';
        if($slot&&$date){$records=array_values(array_filter($this->store->menu($date,(int)$slot['id'],true),fn($r)=>$r['available']));$revision=$this->store->menuRevision($date,(int)$slot['id']);if($query)$records=array_values(array_filter($records,fn($r)=>mb_stripos($r['name'],$query)!==false));foreach($filters as $field=>$value)$records=array_values(array_filter($records,fn($r)=>(bool)$r[$field]===$value));$total=count($records);$page=max(1,min((int)($_GET['page']??1),max(1,(int)ceil($total/30))));$records=array_slice($records,($page-1)*30,30);}
        else{$result=$this->store->pageItems($category?($category['slug']==='shop'?'courier':(isset(Catalog::MEALS[$category['slug']])?'scheduled':'')):$kind,$query,$category?(isset(Catalog::DEFAULTS[$category['slug']])?null:(int)$category['id']):((int)($_GET['category']??0)?:null),(int)($_GET['page']??1),30,$filters,$category?(isset(Catalog::MEALS[$category['slug']])?$category['slug']:''):$meal);$records=$result['records'];$total=$result['total'];$page=$result['page'];}
        $return_url=$_SERVER['REQUEST_URI'];$this->view('items',compact('records','category','base','kind','meal','query','date','slot','revision','total','page','return_url'));return true;
    }
    private function assertCategory(?array $category,array $item):void {if($category&&!(new Catalog($this->store))->contains($category,$item))throw new HttpError(404,'Item not found in this category.');}
    public function categories():array {
        $inventory=new Inventory($this->store);$categories=$this->store->categories();$children=[];foreach($categories as $c)if($c['active'])$children[$c['parent_id']][]=(int)$c['id'];$family=function(int $id)use($children){$seen=[$id=>true];$todo=[$id];while($todo){$parent=array_pop($todo);foreach($children[$parent]??[] as $child)if(!isset($seen[$child])){$seen[$child]=true;$todo[]=$child;}}return array_keys($seen);};$counts=$this->store->db->rows("SELECT i.category_id,COUNT(*) AS total,COUNT(*) FILTER(WHERE i.active AND i.in_stock AND NOT EXISTS(SELECT 1 FROM catalog_inventorybucket v WHERE v.tenant_id=i.tenant_id AND v.item_id=i.id AND v.slot_id IS NULL AND v.tracked AND v.remaining=0 AND i.fulfilment='courier')) AS website FROM catalog_menuitem i WHERE i.tenant_id=? GROUP BY i.category_id",[$this->store->id()]);$map=[];foreach($counts as $row)$map[$row['category_id']]=$row;
        foreach($categories as &$category){$category['total']=$category['website']=0;foreach($family((int)$category['id']) as $id){$category['total']+=(int)($map[$id]['total']??0);$category['website']+=(int)($map[$id]['website']??0);}}unset($category);$catalog=new Catalog($this->store);$items=$this->store->items();foreach($categories as &$category)if(isset(Catalog::DEFAULTS[$category['slug']])){$category['total']=$category['website']=0;foreach($items as $item)if($catalog->contains($category,$item)){if(!$category['image']&&!empty($item['image']))$category['image']=$item['image'];$category['total']++;if($item['active']&&$item['in_stock']&&(!$item['quantity_tracked']||$item['stock_quantity']>0))$category['website']++;}}unset($category);return $categories;
    }
}
