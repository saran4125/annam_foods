<?php
declare(strict_types=1);
namespace Annam;

/** Adapters for features added to the reference after the initial PHP rebuild. */
final class ParityRoutes {
    public function __construct(private Store $store,private array $user,private \Closure $render){}
    private function view(string $view,array $data=[]):void {($this->render)($view,$data,true);}
    private function back(string $fallback):string {$url=$_POST['return_url']??$_GET['return_url']??$fallback;return is_string($url)&&str_starts_with($url,'/manage/')&&!str_contains($url,'\\')?$url:$fallback;}
    public function admin(string $path,string $method):bool {
        if($path==='/manage/customer-lookup/'){if($method!=='GET')throw new HttpError(405,'GET required.');Operations::limit($this->store,'lookup:'.$this->user['id'],60,60);header('Content-Type: application/json');echo json_encode((new CustomerLookup($this->store))->find((string)($_GET['phone']??'')),JSON_THROW_ON_ERROR);return true;}
        if($path==='/manage/reports/'){$service=new Reports($this->store);$report=$service->data($_GET);$sales=$service->sales();if(($_GET['export']??'')==='csv')Reports::csv($report);else $this->view('reports',compact('report','sales'));return true;}
        if($path==='/manage/orders/'){$result=(new Reports($this->store))->orderGroups($_GET);$this->view('orders',$result);return true;}
        if(preg_match('~^/manage/orders/(\d+)/courier/$~',$path,$m)){
            Settings::owner($this->user);if($method!=='POST')throw new HttpError(405,'POST required.');$service=new Courier($this->store);$actor=$this->user['username'];
            if(($_POST['action']??'')==='dispatch')$service->dispatch((int)$m[1],(string)($_POST['amount']??''),(string)($_POST['courier_name']??''),(string)($_POST['tracking_number']??''),$actor);
            elseif(($_POST['action']??'')==='paid'){if(empty($_POST['received']))throw new HttpError(422,'Confirm courier payment was received.');$service->confirm((int)$m[1],(string)($_POST['reference']??''),$actor);}else throw new HttpError(422,'Choose a valid courier action.');redirect('/manage/orders/'.$m[1].'/');
        }
        if($path==='/manage/courier-notices/release/'){Settings::owner($this->user);if($method!=='POST')throw new HttpError(405,'POST required.');$count=(new Courier($this->store))->release();$_SESSION['notice']=$count.' courier notices queued.';redirect('/manage/checkout-settings/');}
        if($path==='/manage/categories/'){
            $categories=$this->categories();$scope=$_GET['category_view']??'populated';$query=trim((string)($_GET['q']??''));$records=array_values(array_filter($categories,fn($c)=>($scope==='all'||($scope==='empty'?$c['total']===0:$c['total']>0))&&(!$query||mb_stripos($c['name'],$query)!==false)));$this->view('categories',compact('records','categories','scope','query'));return true;
        }
        $category=null;$base='/manage/dishes/';
        if(preg_match('~^/manage/categories/(\d+)/items/(.*)$~',$path,$m)){$category=(new Resources($this->store))->get('categories',(int)$m[1]);$base='/manage/categories/'.$category['id'].'/items/';$suffix=$m[2];}
        elseif(str_starts_with($path,$base))$suffix=substr($path,strlen($base));else return false;
        if($suffix==='menu/')return false;
        if(preg_match('~^(\d+)/(stock|toggle|archive)/$~',$suffix,$m)){
            if($method!=='POST')throw new HttpError(405,'Use the action form.');$item=$this->store->item((int)$m[1]);$this->assertCategory($category,$item);
            if($m[2]==='stock')$this->store->db->rows('UPDATE catalog_menuitem SET in_stock=NOT in_stock WHERE tenant_id=? AND id=?',[$this->store->id(),$item['id']]);
            elseif($m[2]==='toggle'&&!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],(int)$item['id'],!empty($_POST['available']),(int)$_POST['revision']);
            elseif($m[2]==='archive'&&!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],(int)$item['id'],false,(int)$_POST['revision']);
            elseif($m[2]==='archive')(new Resources($this->store))->removeFromSale('dishes',(int)$item['id']);else (new Resources($this->store))->toggle('dishes',(int)$item['id']);redirect($this->back($base));
        }
        if(preg_match('~^(new|\d+)/$~',$suffix,$m)){
            $key='dishes';$spec=Resources::definition($key);$id=$m[1]==='new'?null:(int)$m[1];$record=$id?$this->store->item($id):['active'=>true,'in_stock'=>true,'is_veg'=>true,'sort'=>0,'price'=>'0','fulfilment'=>$_GET['kind']??'courier','category_id'=>$category['id']??null];if($id)$this->assertCategory($category,$record);$return_url=$this->back($base);$fixed_category_id=$category?($record['category_id']??$category['id']):null;
            if($method==='POST'){$input=$_POST;if($category)$input['category_id']=$fixed_category_id;$this->store->db->transaction(function()use($id,$input){$saved=(new Resources($this->store))->save('dishes',$id,$input,$_FILES);if(!empty($_POST['menu_date']))$this->store->setDayAvailability(Store::date($_POST['menu_date']),(int)$_POST['menu_slot_id'],$saved,!empty($_POST['day_available']),(int)$_POST['day_revision']);});$_SESSION['notice']='Item saved.';redirect($return_url);}
            $this->view('resource-edit',compact('key','spec','id','record','return_url','fixed_category_id'));return true;
        }
        if($suffix!=='')return false;
        $kind=(string)($_GET['kind']??$_GET['type']??'scheduled');if(!in_array($kind,['scheduled','courier'],true))$kind='scheduled';$meal=(string)($_GET['meal']??'');$query=mb_substr(trim((string)($_GET['q']??'')),0,80);$date=($_GET['date']??'')==='all'?null:Store::date((string)($_GET['date']??date('Y-m-d')));$slot=null;$revision=0;
        if(!$category&&$kind==='scheduled'&&$meal&&$meal!=='unassigned')$slot=$this->store->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$meal]);
        $filters=[];foreach(['stock'=>'in_stock','status'=>'active'] as $param=>$field)if(isset($_GET[$param])&&in_array($_GET[$param],['0','1'],true))$filters[$field]=$_GET[$param]==='1';
        if($slot&&$date){$records=$this->store->menu($date,(int)$slot['id'],true);$revision=$this->store->menuRevision($date,(int)$slot['id']);if($query)$records=array_values(array_filter($records,fn($r)=>mb_stripos($r['name'],$query)!==false));foreach($filters as $field=>$value)$records=array_values(array_filter($records,fn($r)=>(bool)$r[$field]===$value));$total=count($records);$page=max(1,min((int)($_GET['page']??1),max(1,(int)ceil($total/30))));$records=array_slice($records,($page-1)*30,30);}
        else{$result=$this->store->pageItems($category?'':$kind,$query,$category?(int)$category['id']:null,(int)($_GET['page']??1),30,$filters,$category?'':$meal);$records=$result['records'];$total=$result['total'];$page=$result['page'];}
        $return_url=$_SERVER['REQUEST_URI'];$this->view('items',compact('records','category','base','kind','meal','query','date','slot','revision','total','page','return_url'));return true;
    }
    private function assertCategory(?array $category,array $item):void {if($category&&!in_array((int)$item['category_id'],$this->store->family((int)$category['id']),true))throw new HttpError(404,'Item not found in this category.');}
    public function categories():array {
        $categories=$this->store->categories();$children=[];foreach($categories as $c)if($c['active'])$children[$c['parent_id']][]=(int)$c['id'];$family=function(int $id)use($children){$seen=[$id=>true];$todo=[$id];while($todo){$parent=array_pop($todo);foreach($children[$parent]??[] as $child)if(!isset($seen[$child])){$seen[$child]=true;$todo[]=$child;}}return array_keys($seen);};$counts=$this->store->db->rows("SELECT category_id,COUNT(*) AS total,COUNT(*) FILTER(WHERE active AND in_stock AND fulfilment='courier') AS website FROM catalog_menuitem WHERE tenant_id=? GROUP BY category_id",[$this->store->id()]);$map=[];foreach($counts as $row)$map[$row['category_id']]=$row;
        foreach($categories as &$category){$category['total']=$category['website']=0;foreach($family((int)$category['id']) as $id){$category['total']+=(int)($map[$id]['total']??0);$category['website']+=(int)($map[$id]['website']??0);}}unset($category);return $categories;
    }
}
