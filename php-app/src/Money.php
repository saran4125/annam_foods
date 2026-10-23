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
}
