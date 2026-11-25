<?php declare(strict_types=1); namespace Annam; $title='Delete category';$subtitle=$category['name']; ?>
<a class="o-crumb" href="/manage/categories/?category_view=all">← Categories</a>
<section class="o-card"><h2>Delete <?= e($category['name']) ?>?</h2>
<p>This removes the category only. Its <?= e($itemCount) ?> dishes and products will be kept without a category. You can assign them to another category in Dishes &amp; products.</p>
<?php if($childCount):?><p><?= e($childCount) ?> subcategories will be kept as separate categories.</p><?php endif;?>
<p>Existing orders, bills, stock and saved daily menus are kept.</p>
<form method="post"><?= csrf() ?><input type="hidden" name="confirmed" value="yes"><div class="o-btn-row"><a class="o-btn" href="/manage/categories/?category_view=all">Cancel</a><button class="o-btn o-btn-primary" type="submit">Delete category</button></div></form></section>
