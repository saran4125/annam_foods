<?php
declare(strict_types=1);
namespace Annam;
final class Markdown {
    public static function render(string $text): string {
        require_once ANNAM_ROOT.'/resources/vendor/parsedown/Parsedown.php';
        $parser=new \Parsedown();$parser->setSafeMode(true);$parser->setBreaksEnabled(true);return $parser->text($text);
    }
}
