<?php
declare(strict_types=1);
namespace Annam;

/** Exact decimal input/output. Minor units are confined to monetary operations. */
final class Money {
    public static function parse(string $value): int {
        if (!preg_match('/^(0|[1-9][0-9]{0,7})(?:\.([0-9]{1,2}))?$/D', $value, $matches)) {
            throw new \InvalidArgumentException('Enter a nonnegative amount with at most two decimal places.');
        }
        return ((int)$matches[1]) * 100 + (int)str_pad($matches[2] ?? '', 2, '0');
    }
    public static function decimal(int $minor): string {
        if ($minor < 0) throw new \InvalidArgumentException('Amount cannot be negative.');
        return intdiv($minor, 100) . '.' . str_pad((string)($minor % 100), 2, '0', STR_PAD_LEFT);
    }
    public static function display(int $minor): string { return '₹' . self::decimal($minor); }
    public static function signedDecimal(int $minor): string { return ($minor<0?'-':'').self::decimal(abs($minor)); }
    public static function signedParse(string $value): int { return str_starts_with($value,'-')?-self::parse(substr($value,1)):self::parse($value); }
    public static function ratio(int $numerator, int $denominator): int {
        if($numerator<0 || $denominator<1) throw new \InvalidArgumentException('Invalid monetary ratio.');
        return intdiv($numerator,$denominator)+(2*($numerator%$denominator)>=$denominator?1:0);
    }
    public static function tax(int $gross, int $rate, bool $inclusive): array {
        if($rate<0||$rate>10000) throw new \InvalidArgumentException('Tax rate must be between 0 and 100.');
        $base=$inclusive?self::ratio($gross*10000,10000+$rate):$gross;
        return ['base'=>$base,'tax'=>$inclusive?$gross-$base:self::ratio($base*$rate,10000)];
    }
}
