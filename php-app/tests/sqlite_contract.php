<?php
declare(strict_types=1);
require dirname(__DIR__).'/src/bootstrap.php';
use Annam\{Database,SqliteDialect};
if(PHP_SAPI!=='cli')exit(1);
$expected='2026-11-03 04:10:22.123456';foreach(['2026-11-03 04:10:22.123456','2026-11-03T04:10:22.123456Z','2026-11-03T09:40:22.123456+05:30'] as $value)if(SqliteDialect::timestamp($value)!==$expected)throw new RuntimeException('UTC normalization changed time or precision.');echo "PASS canonical SQLite timestamps preserve UTC, explicit offsets and microseconds\n";
$db=new Database(new PDO('sqlite::memory:'));$db->rows('CREATE TABLE money_fixture(total DECIMAL_TEXT NOT NULL)');$db->rows('INSERT INTO money_fixture(total) VALUES(?)',['0.10']);$db->rows('INSERT INTO money_fixture(total) VALUES(?)',['0.20']);if($db->one('SELECT SUM(total) AS amount FROM money_fixture')['amount']!=='0.30')throw new RuntimeException('Money aggregate used floating point.');echo "PASS SQLite currency totals are exact decimal strings\n";
$body='2026-11-03T09:40:22+05:30';$params=SqliteDialect::parameters('INSERT INTO messaging_whatsappmessage(body,occurred_at) VALUES(?,?)',[$body,$body]);if($params[0]!==$body||$params[1]!=='2026-11-03 04:10:22.000000')throw new RuntimeException('Timestamp conversion changed message content.');echo "PASS timestamp binding does not rewrite date-like message text\n";
