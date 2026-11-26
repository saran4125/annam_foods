<?php
declare(strict_types=1);
namespace Annam;

/** Numbered positions belong to a meal library, independently for shared dishes. */
final class DisplayOrder {
    public function __construct(private Store $store){}
    public static function position(array $item,string $group):int { $positions=json_decode($item['display_positions']??'{}',true)?:[];return (int)($positions[$group]??$item['sort']); }
    public static function sql(string $group):string {return isset(Catalog::DEFAULTS[$group])?"COALESCE(CAST(i.display_positions->>'$group' AS INTEGER),i.sort)":'i.sort';}
    public static function compare(array $a,array $b,string $group):int {return [self::position($a,$group),-$a['sort_priority'],$a['name'],$a['id']]<=>[self::position($b,$group),-$b['sort_priority'],$b['name'],$b['id']];}
    public function move(int $id,int $requested,?string $group,array $previous,array $input):void {
        $catalog=new Catalog($this->store);$rows=$this->store->items();$memberships=[];$target=null;
        foreach($rows as $i=>$row){
            $keys=$row['fulfilment']==='courier'?['shop']:$catalog->meals($row);
            if((int)$row['id']===$id){
                if($row['fulfilment']==='scheduled'&&!empty($input['meals_present'])){
                    $keys=$input['meals']??[];if(!is_array($keys)||array_diff($keys,array_keys(Catalog::MEALS)))throw new HttpError(422,'Choose valid meals.');
                }
                if($previous)$rows[$i]['sort']=$previous['sort'];$target=$rows[$i];$targetKeys=$keys;
            }
            $memberships[(int)$row['id']]=$keys;
        }
        if(!$target||!$targetKeys)return;
        $group=in_array($group,$targetKeys,true)?$group:$targetKeys[0];$positions=[];foreach($rows as $row)$positions[(int)$row['id']]=[];
        foreach(array_keys(Catalog::DEFAULTS) as $key){
            $all=array_values(array_filter($rows,fn($row)=>in_array($key,$memberships[(int)$row['id']],true)));
            usort($all,fn($a,$b)=>self::compare($a,$b,$key));$peers=array_values(array_filter($all,fn($row)=>(int)$row['id']!==$id));
            if(in_array($key,$targetKeys,true)){
                if($key===$group)$index=max(0,min($requested-1,count($peers)));
                elseif(!$previous)$index=count($peers);
                else $index=array_search($id,array_map('intval',array_column($all,'id')),true);
                array_splice($peers,(int)$index,0,[$target]);
            }
            foreach($peers as $index=>$row)$positions[(int)$row['id']][$key]=$index+1;
        }
        foreach($rows as $row){$value=$positions[(int)$row['id']];if((json_decode($row['display_positions']??'{}',true)?:[])!==$value)$this->store->db->rows('UPDATE catalog_menuitem SET display_positions=? WHERE tenant_id=? AND id=?',[json_encode($value?:new \stdClass(),JSON_THROW_ON_ERROR),$this->store->id(),$row['id']]);}
        $this->store->db->rows('UPDATE catalog_menuitem SET sort=? WHERE tenant_id=? AND id=?',[$positions[$id][$group],$this->store->id(),$id]);
    }
}
