<?php
declare(strict_types=1);
namespace Annam;
/** The small, audited SQL compatibility boundary; application prices stay decimal text. */
final class SqliteDialect {
    private static function types():array {static $types;return $types??=json_decode(file_get_contents(ANNAM_ROOT.'/resources/sqlite-types.json'),true,512,JSON_THROW_ON_ERROR);}
    public static function timestamp(string $value):string {return (new \DateTimeImmutable($value,new \DateTimeZone('UTC')))->setTimezone(new \DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');}
    public static function parameters(string $sql,array $params):array {
        $types=self::types();$times=[];foreach($types as $fields)foreach($fields as $name=>$type)if($type==='TIMESTAMP')$times[$name]=true;
        $columns=[];
        if(preg_match('/^\s*INSERT\s+INTO\s+\w+\s*\(([^)]+)\)\s*VALUES\s*\((.*)\)/is',$sql,$m)){
            $names=array_map(fn($v)=>trim($v," \t\n\r\""),explode(',',$m[1]));$expressions=self::split($m[2]);$n=0;foreach($expressions as $i=>$expression)for($j=0;$j<substr_count($expression,'?');$j++)$columns[$n++]=$names[$i]??'';
        }else{preg_match_all('/([^?]*)\?/s',$sql,$matches);foreach($matches[1] as $i=>$prefix)if(preg_match('/(?:\b\w+\.)?"?(\w+)"?\s*(?:=|>=|<=|>|<)\s*$/',$prefix,$m))$columns[$i]=$m[1];}
        foreach($params as $i=>$value)if(is_string($value)&&isset($times[$columns[$i]??''])&&preg_match('/^\d{4}-\d\d-\d\d[T ]\d\d:\d\d/',$value))$params[$i]=self::timestamp($value);
        return $params;
    }
    private static function split(string $value):array {$result=[];$depth=0;$quote=false;$start=0;for($i=0;$i<strlen($value);$i++){if($value[$i]==="'"){$quote=!$quote;}if(!$quote){if($value[$i]==='(')$depth++;elseif($value[$i]===')')$depth--;elseif($value[$i]===','&&$depth===0){$result[]=substr($value,$start,$i-$start);$start=$i+1;}}}$result[]=substr($value,$start);return $result;}
    public static function sql(string $sql):string {
        $sql=preg_replace('/\s+FOR UPDATE(?:\s+OF\s+\w+)?(?:\s+SKIP LOCKED)?/i','',$sql);
        $sql=preg_replace_callback("/CURRENT_TIMESTAMP\s*-\s*INTERVAL\s*'(\d+)\s+(minutes?|hours?|days?)'/i",fn($m)=>"(strftime('%Y-%m-%d %H:%M:%f','now','-".$m[1].' '.$m[2]."') || '000')",$sql);
        $sql=preg_replace('/\bCURRENT_TIMESTAMP\b/i',"(strftime('%Y-%m-%d %H:%M:%f','now') || '000')",$sql);
        $sql=preg_replace('/\bILIKE\b/i','LIKE',$sql);
        $sql=str_replace('CROSS JOIN LATERAL jsonb_array_elements(o.items) line','JOIN json_each(o.items) line',$sql);
        $sql=str_replace('LEFT JOIN LATERAL jsonb_array_elements(o.items) line ON true','LEFT JOIN json_each(o.items) line ON true',$sql);
        $sql=preg_replace_callback("/\bline->>'([a-z_]+)'/",fn($m)=>"json_extract(line.value,'$.".$m[1]."')",$sql);
        // Money aggregates use integer paise internally, never SQLite floating-point SUM.
        $offset=0;while(preg_match('/\bSUM\(/i',$sql,$match,PREG_OFFSET_CAPTURE,$offset)){$start=$match[0][1];$open=$start+strlen($match[0][0])-1;$depth=1;$quote=false;$end=$open;while(++$end<strlen($sql)&&$depth){$c=$sql[$end];if($c==="'")$quote=!$quote;if(!$quote){if($c==='(')$depth++;elseif($c===')')$depth--;}}$expression=substr($sql,$open+1,$end-$open-2);$money=preg_match('/\b(?:total|line_total)\b/',$expression)||(str_contains($sql,'FROM orders_couriercharge')&&preg_match('/\bamount\b/',$expression));if($money){$sql=substr_replace($sql,'money_sum',$start,3);$end+=6;}$offset=$end;}
        return preg_replace('/::(?:text|numeric|integer|bigint|uuid|jsonb)\b/i','',$sql);
    }
    public static function register(\PDO $pdo):void {
        $pdo->sqliteCreateFunction('to_timestamp',fn($seconds)=>gmdate('Y-m-d H:i:s',(int)$seconds).'.000000',1);
        $pdo->sqliteCreateFunction('decimal_paise',fn($amount)=>Money::parse((string)$amount),1);
        $pdo->sqliteCreateAggregate('money_sum',function(&$context,$count,$amount){$context=($context??0)+($amount===null?0:Money::parse((string)$amount));return $context;},fn(&$context,$count)=>Money::decimal($context??0),1);
        $pdo->sqliteCreateAggregate('meal_group',function(&$context,$count,$key){$context??=[];if($key!==null)$context[(string)$key]=true;return $context;},function(&$context,$count){$keys=array_keys($context??[]);sort($keys);return implode('+',$keys);},1);
    }
    public static function results(array $rows):array {
        $types=self::types();$times=[];$booleans=[];foreach($types as $fields)foreach($fields as $name=>$type){if($type==='TIMESTAMP')$times[$name]=true;if($type==='BOOLEAN')$booleans[$name]=true;}
        foreach($rows as &$row)foreach($row as $key=>&$value)if(isset($booleans[$key])&&$value!==null)$value=(bool)$value;elseif(isset($times[$key])&&is_string($value)&&preg_match('/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?$/D',$value))$value=str_replace(' ','T',$value).'Z';unset($row,$value);return $rows;
    }
}
