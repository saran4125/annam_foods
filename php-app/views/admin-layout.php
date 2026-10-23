<?php declare(strict_types=1); namespace Annam; ?>
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= e($title ?? 'Store admin') ?> · <?= e($store->name()) ?></title>
<meta name="robots" content="noindex,nofollow">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Figtree:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="/assets/owner.css"><link rel="stylesheet" href="/assets/php.css"></head><body class="o-body">
<?php require __DIR__ . '/icons.php'; ?>
<aside class="o-side" data-side id="o-side"><a class="o-brand" href="/manage/"><img src="<?= e($store->logo()) ?>" alt="" width="44"><span><?= e($store->name()) ?><small>Store admin</small></span></a>
<nav class="o-nav" aria-label="Administration">
<?php foreach (['/manage/' => ['Dashboard','home'], '/manage/dishes/' => ['Dishes & products','dish'], '/manage/dishes/menu/' => ['Daily menus','clock'], '/manage/categories/' => ['Categories','grid'], '/manage/slots/' => ['Meal times','clock'], '/manage/zones/' => ['Delivery areas','pin'], '/manage/banners/' => ['Offer banners','image'], '/manage/pages/' => ['Website pages','page'], '/manage/settings/' => ['Store settings','cog']] as $url => [$label,$icon]): ?>
<a href="<?= e($url) ?>" class="<?= $path === $url ? 'on' : '' ?>"><svg class="o-ic" aria-hidden="true"><use href="#o-<?= e($icon) ?>"/></svg><?= e($label) ?></a>
<?php endforeach; ?></nav><div class="o-side-foot"><a class="o-ghost" href="/" target="_blank">View website ↗</a><form method="post" action="/manage/logout/"><?= csrf() ?><button class="o-ghost" type="submit">Log out <small><?= e($user['username']) ?></small></button></form></div></aside>
<div class="o-scrim" data-scrim hidden></div>
<div class="o-shell"><header class="o-top"><button class="o-burger" type="button" data-burger aria-label="Open menu" aria-controls="o-side" aria-expanded="false">☰</button><div class="o-top-title"><h1><?= e($title ?? 'Store admin') ?></h1><p><?= e($subtitle ?? 'Annam Foods') ?></p></div></header>
<div class="php-preview">PHP preview · Test database · Checkout, payments, billing and WhatsApp are still being migrated.</div>
<?php if ($notice): ?><div class="o-flashes"><p class="o-flash" role="status"><?= e($notice) ?></p></div><?php endif; ?>
<main class="o-main" id="o-main"><?= $content ?></main></div><script src="/assets/owner.js" defer></script></body></html>
