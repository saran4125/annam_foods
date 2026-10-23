<?php declare(strict_types=1); namespace Annam; $title=$page['title'].' · '.$store->name(); ?>
<article class="wrap php-store-section php-prose"><h1><?= e($page['title']) ?></h1><div><?= Markdown::render($page['body_md']) ?></div></article>
