<?php
declare(strict_types=1);
namespace Annam;

final class Reports {
    public function __construct(private Store $store){}
    public static function mealExpression():string {return "COALESCE(NULLIF(line->>'meal_key',''),s.key,CASE WHEN o.fulfilment='courier' THEN 'snacks' ELSE 'unclassified' END)";}
    public function data(array $input):array {
        try{$start=new \DateTimeImmutable((string)($input['start']??date('Y-m-d').'T00:00'));$end=new \DateTimeImmutable((string)($input['end']??date('Y-m-d\TH:i:s',time()+1)));}catch(\Exception){throw new HttpError(422,'Choose valid start and end dates/times.');}
        if($end<=$start)throw new HttpError(422,'End must be after start. The end time is excluded.');
        $condition="o.tenant_id=? AND o.placed_at>=? AND o.placed_at<? AND NOT EXISTS(SELECT 1 FROM payments_paymentintent p WHERE p.tenant_id=o.tenant_id AND p.order_id=o.id AND p.mode='test')";$params=[$this->store->id(),$start->format('c'),$end->format('c')];
        if(empty($input['include_cancelled']))$condition.=" AND o.status<>'cancelled'";
        if(!empty($input['delivery_date'])){$condition.=' AND o.delivery_date=?';$params[]=Store::date($input['delivery_date']);}
        if(!empty($input['meal'])){if(!in_array($input['meal'],['breakfast','lunch','dinner','snacks'],true))throw new HttpError(422,'Choose a valid food category.');$condition.=' AND '.self::mealExpression().'=?';$params[]=$input['meal'];}
        if(!empty($input['product'])){$q=mb_substr((string)$input['product'],0,120);$condition.=" AND ((line->>'name') ILIKE ? OR line->>'item_id'=?)";array_push($params,'%'.$q.'%',$q);}
        $from=" FROM orders_order o LEFT JOIN catalog_slot s ON s.id=o.slot_id AND s.tenant_id=o.tenant_id CROSS JOIN LATERAL jsonb_array_elements(o.items) line WHERE ".$condition;
        $rows=$this->store->db->rows("SELECT ".self::mealExpression()." AS meal,COALESCE(line->>'item_id','') AS product_id,line->>'name' AS product,COALESCE(line->>'category_name','') AS catalog_category,SUM((line->>'quantity')::integer) AS quantity,SUM((line->>'line_total')::numeric)::text AS amount,COUNT(DISTINCT o.id) AS orders".$from.' GROUP BY 1,2,3,4 ORDER BY 1,3',$params);
        $totals=$this->store->db->one("SELECT COUNT(*) AS order_count,COALESCE(SUM(total),0)::text AS order_value,COALESCE(SUM(CASE WHEN payment_status='paid' THEN total ELSE 0 END),0)::text AS paid_order_value FROM (SELECT DISTINCT o.id,o.total,o.payment_status".$from.') selected',$params);
        return ['rows'=>$rows,'start'=>$start->format('Y-m-d\TH:i'),'end'=>$end->format('Y-m-d\TH:i'),'order_count'=>(int)$totals['order_count'],'order_value'=>$totals['order_value'],'paid_order_value'=>$totals['paid_order_value'],'quantity'=>array_sum(array_column($rows,'quantity')),'items_amount'=>Money::decimal(array_sum(array_map(fn($r)=>Money::parse($r['amount']),$rows)))];
    }
    public function sales():array {
        $start=date('Y-m-d').'T00:00:00'.date('P');$end=date('c');$t=$this->store->id();
        $base=" FROM orders_order o WHERE o.tenant_id=? AND o.placed_at>=? AND o.placed_at<=? AND o.status<>'cancelled' AND NOT EXISTS(SELECT 1 FROM payments_paymentintent p WHERE p.tenant_id=o.tenant_id AND p.order_id=o.id AND p.mode='test')";
        $row=$this->store->db->one("SELECT COUNT(*) AS order_count,COALESCE(SUM(total),0)::text AS order_value,COALESCE(SUM(CASE WHEN payment_status='paid' THEN total ELSE 0 END),0)::text AS paid_order_value,COALESCE(SUM(CASE WHEN payment_status IN ('pending','cod_pending','failed') THEN total ELSE 0 END),0)::text AS pending_order_value".$base,[$t,$start,$end]);
        $manual=$this->store->db->one("SELECT COALESCE(SUM(o.total),0)::text AS amount FROM orders_order o WHERE o.tenant_id=? AND EXISTS(SELECT 1 FROM orders_orderevent e WHERE e.tenant_id=o.tenant_id AND e.order_id=o.id AND e.at>=? AND e.at<=? AND e.note LIKE 'Payment receipt confirmed.%') AND NOT EXISTS(SELECT 1 FROM payments_paymentintent p WHERE p.tenant_id=o.tenant_id AND p.order_id=o.id AND p.mode='test')",[$t,$start,$end]);
        $online=$this->store->db->one("SELECT COALESCE(SUM(amount),0)::bigint AS amount FROM payments_paymentintent WHERE tenant_id=? AND mode='live' AND captured_at>=? AND captured_at<=?",[$t,$start,$end]);
        $refunds=$this->store->db->one("SELECT COALESCE(SUM(r.amount),0)::bigint AS amount FROM payments_refund r JOIN payments_paymentintent p ON p.id=r.intent_id AND p.tenant_id=r.tenant_id WHERE r.tenant_id=? AND p.mode='live' AND r.state='processed' AND r.processed_at>=? AND r.processed_at<=?",[$t,$start,$end]);
        $courier=$this->store->db->one('SELECT COALESCE(SUM(amount),0)::text AS amount FROM orders_couriercharge WHERE tenant_id=? AND paid_at>=? AND paid_at<=?',[$t,$start,$end]);
        return $row+['as_of'=>$end,'manual_receipts'=>$manual['amount'],'online_receipts'=>Money::decimal((int)$online['amount']),'refunds'=>Money::decimal((int)$refunds['amount']),'courier_receipts'=>$courier['amount'],'net_receipts'=>Money::decimal(Money::parse($manual['amount'])+(int)$online['amount']+Money::parse($courier['amount'])-(int)$refunds['amount'])];
    }
    public function orderGroups(array $input):array {
        $meal="COALESCE(NULLIF(line->>'meal_key',''),s.key,CASE WHEN o.fulfilment='courier' THEN 'snacks' ELSE 'unclassified' END)";
        $cte="WITH grouped AS (SELECT o.id,COALESCE(string_agg(DISTINCT ".$meal.", '+' ORDER BY ".$meal."),'unclassified') AS meal_group FROM orders_order o LEFT JOIN catalog_slot s ON s.id=o.slot_id AND s.tenant_id=o.tenant_id LEFT JOIN LATERAL jsonb_array_elements(o.items) line ON true WHERE o.tenant_id=? GROUP BY o.id) ";
        $counts=$this->store->db->rows($cte.'SELECT meal_group,COUNT(*) AS n FROM grouped GROUP BY meal_group ORDER BY meal_group',[$this->store->id()]);$groups=[];foreach($counts as $r)$groups[$r['meal_group']]=(int)$r['n'];
        $where=' WHERE o.tenant_id=?';$args=[$this->store->id(),$this->store->id()];
        foreach(['meal_group'=>'g.meal_group','status'=>'o.status','channel'=>'o.channel'] as $key=>$column)if(!empty($input[$key])){$where.=' AND '.$column.'=?';$args[]=mb_substr((string)$input[$key],0,100);}
        if($q=mb_substr(trim((string)($input['q']??'')),0,100)){$where.=' AND (o.order_no ILIKE ? OR c.name ILIKE ? OR c.phone ILIKE ?)';array_push($args,'%'.$q.'%','%'.$q.'%','%'.$q.'%');}
        $from=' FROM grouped g JOIN orders_order o ON o.id=g.id JOIN orders_customer c ON c.id=o.customer_id AND c.tenant_id=o.tenant_id'.$where;$total=(int)$this->store->db->one($cte.'SELECT COUNT(*) AS n'.$from,$args)['n'];$page=max(1,min((int)($input['page']??1),max(1,(int)ceil($total/50))));
        $records=$this->store->db->rows($cte.'SELECT o.*,c.name AS customer_name,c.phone AS customer_phone,g.meal_group'.$from.' ORDER BY o.placed_at DESC,o.id DESC LIMIT 50 OFFSET '.(($page-1)*50),$args);
        foreach($records as &$row)$row['meal_label']=implode(' + ',array_map('ucfirst',explode('+',$row['meal_group'])));unset($row);
        return compact('records','groups','total','page');
    }
    public static function csv(array $report):void {
        header('Content-Type: text/csv; charset=utf-8');header('Content-Disposition: attachment; filename="annam-order-report.csv"');$file=fopen('php://output','wb');fwrite($file,"\xEF\xBB\xBF");fputcsv($file,['Start (inclusive)',$report['start'],'End (exclusive)',$report['end']]);fputcsv($file,['Food category','Product ID','Product','Catalog category','Quantity','Items amount (INR)','Order count']);
        foreach($report['rows'] as $row)fputcsv($file,array_map(fn($v)=>preg_match('/^[=+@\-\t\r]/',(string)$v)?"'".$v:$v,array_values($row)));fclose($file);
    }
}
