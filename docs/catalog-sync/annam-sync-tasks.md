# Annam Foods: sync build site with live site

Build site: https://annam-foods.onrender.com (this project)
Live site (source of truth): https://www.annamfood.in
Compared on: 30 Oct 2026. Prices are in INR. Live prices are taken from category listing cards. Pack sizes were not visible on live, so leave `weight` empty or ask the owner for it.

Build currently has 141 shop products in 11 categories. Do the tasks below in order. Do not delete any existing build products unless a task says so.

---

## TASK 1: Add missing in-stock products (29)

Create each product with the category shown. Image and weight are not available, so use a placeholder image and leave weight blank. Flag these in the admin as "needs photo and weight".

### Pakshanams (category: Pakshanams)
| Name | Price |
|---|---|
| Spl Milagu Vadai | 130 |
| Madras Mixture | 170 |
| Moru Moru Murukku | 140 |
| Mani Murukku | 150 |
| Aval Mixture | 140 |
| Vella Seedai | 170 |

### Chips (category: Chips)
| Name | Price |
|---|---|
| Finger Chips | 80 |
| Jack Fruit Chips | 100 |
| Wheel Chips | 80 |
| Tapioca Chips | 90 |
| Corn Chips | 80 |
| Chips Combo Pack | 300 |

### Sweets and Laddus
| Name | Price | Category |
|---|---|---|
| Ghee Appam | 175 | Sweets |
| Cashew Halwa | 200 | Halwa |
| Kalyana Mysurpa | 190 | Sweets |
| Spl Wheat Halwa | 200 | Halwa |
| Rava Laddu | 70 | Millets Laddus |
| Pori Urundai | 90 | Millets Laddus |

### Pickles
| Name | Price |
|---|---|
| Mavadu Salt Pickle | 450 |
| Mixed Vegetable Pickle | 170 |

### Vathal & Vadagams
| Name | Price |
|---|---|
| Ila Vadam | 160 |
| Javvarisi Vadam Karam | 140 |

### Appalams
| Name | Price |
|---|---|
| Ulundhu Appalam | 140 |
| Ulundhu Appalam - Jeera | 150 |

### Health Products
| Name | Price |
|---|---|
| Spl Ilantha Vadai | 170 |
| Inji Murappa | 90 (live shows a discount from 110) |
| Sukku Coffee Powder Mix | 120 |
| Sukku-Milagu-Thippli-Panai Karuppathi Cake | 120 |
| Deepavali Legiyam | 180 |

---

## TASK 2: Add a Diwali 2026 category (currently missing)

The homepage banner "Diwali 2026 sweets & pakshanams" links to /shop/, but no Diwali products exist. Create a category "Diwali 2026" (slug `diwali-2026`) with sub-groups Combos, Sweets and Karams. Point the banner button to `/shop/diwali-2026/`. Delivery dates are 5 Nov and 7 Nov 2026, as in the existing banner text.

### Combos
| Name | Price |
|---|---|
| Diwali - Mega Combo Pack | 1800 |
| Diwali - Karam Combo Pack | 700 |
| Diwali - Sweets Combo Pack | 900 |
| Diwali - Mini Gift Combo | 650 |

### Sweets
| Name | Price |
|---|---|
| Diwali - Assorted Sweets 250gm | 230 |
| Diwali - Assorted Sweets 500gm | 360 |
| Diwali - Kaju Assorted Sweets 250gm | 400 |
| Diwali - Kaju Assorted Sweets 500gm | 750 |
| Diwali - Jangiri | 190 |
| Diwali - Badhusha | 190 |
| Diwali - Kalyana Mysurpa | 190 |
| Diwali - Laddu | 190 |
| Diwali - Kaju Kathli | 330 |
| Diwali - Horlicks Burfi | 280 |
| Diwali - Boost Burfi | 280 |
| Diwali - Tirunelveli Halwa | 200 |
| Diwali - Athirasam | 170 |
| Diwali - Manogaram | 170 |
| Diwali Legiyam | 180 |
| Rava Laddu (5) | 80 |

### Karams
| Name | Price |
|---|---|
| Diwali - Spl Mixture | 170 |
| Diwali - Navadhanya Mixture | 170 |
| Diwali - Ribbon Pakkoda | 150 |
| Diwali - Karaboondhi | 150 |
| Diwali - Karasev | 150 |
| Diwali - Omapodi | 150 |
| Diwali - Butter Murukku | 150 |
| Diwali - Spl Thattai | 150 |
| Diwali - Moru Moru Murukku | 140 |

Note: Diwali Legiyam, Diwali Karam Combo Pack and Diwali Sweets Combo Pack appear in more than one live Diwali sub-category. Support products belonging to several categories if the data model allows it. Otherwise, use the primary group above.

---

## TASK 3: Fix price mismatches

Live is the source of truth. Confirm with the owner before changing Mavadu Karam, since the pack size may differ.

| Product | Build now | Change to |
|---|---|---|
| Health Pakshanams Combo | 250 | 320 |
| Black Ellu Urundai 100 gm | 100 | 120 |
| Pottu Kadalai Urundai | 100 | 120 |
| Mini Kadalai Urundai | 100 | 120 |
| Mango Ginger Pickle | 150 | 160 |
| Mavadu Karam | 280 | 450 (verify pack size) |

---

## TASK 4: Add out-of-stock products (47), hidden or marked "Out of stock"

Live shows these as sold out. Add them with an `in_stock = false` flag so they show "Out of stock" (or are hidden) and can be switched on later.

- **Podi:** Dhaniya Thool 95, Thani Milagai Thool 95, Manjal Thool 95
- **Pakshanams:** Nendram Sweet Chips 150, Big Pepper Thattai 160, Kamar Kattu 110, Gram Dhall 70, Moong Dhall 70, Onion Ring Chips 80, Honey Mittai 75, Navadhanya Mixture 170, Fried Bengal Gram 80, Pavakkai Chips 100, 2 Suttu Murukku 170, Ribbon Pakkoda 150, Masala Pori 80
- **Sweets:** Kaju Kathli 350, Spl Milk Halwa 240, Karupatti Halwa 280, Ghee Mysurpa 200, Carrot Halwa 190, Horlics Burfi 260, Trattippal 190, Spl Laddu 190
- **Pickles and Thokku:** Arusuvai Thokku 280, Mudavattkkal Kizangu Thokku 280, Onion Thokku 160, Vallarai Thokku 200, Andra Avakkai Pickle 210, Mango Ginger Salt 150, Narthangai Salt Pickle 150, Amla Pickle 170
- **Vathal:** Tamarai Thandu Vadam 220, Kothavarai Vathal 100, Gundu Moremilagai 90, Kara Murukku Vadam 175, Sambar Vadam 180, Ompodi Vadam Small 180, Arulu Sandigai 225, Narthangai Dry Karam Vathal 90, Ila Vadam - Red Chilly 160
- **Appalams:** Ulundhu Appalam - Omam 140, Red Chilly Appala Poo 70, Mini Milagu Appalam 70, Kerala Pappadam 90
- **Health:** Karuppu Kavuni Kanji Mix 270, Honey Amla Dry 90

---

## TASK 5: Stock sync

The build shows "Add" on every product, but live marks some as out of stock. Set `in_stock = false` on these build products so they match live:

Mudakkathan Thokku, Poriyal Podi, Idly Podi, Curry Leaves Podi (build name "Curry Leaves Podi"), Angaya Podi, Omapodi, Kerala Mixture, Mini Thenkuzal 200gm, Vazhaikkai Karam, Vazhaikkai Pepper, Mini Jangiri, Palgova, Thuthuvalai Thokku, Small Onion Garlic Chutney, Kadarangai Pickle, Lemon Pickle, Mango Thokku (101), Cut Mango Pickle, Milagu Kuzambu Mix, Sundaikkai Salt Vathal, Narthangai Dry Vathal, Neetu Moremilagai, Thalir Vadam - Big, Special mini Thattai, Rettai Appalam, Garlic Appala Poo, Corn Vathal, Karuppu Ulundhu Laddu (5), Karuppu Ulundhu Kanji Mix.

Longer term, add an admin stock toggle on every product and make the shop and cart respect it. The cart must not allow adding out-of-stock items.

---

## TASK 6: Items in build but not on live (owner decision, do NOT delete)

Mark these "Build only" in a note and ask the owner whether they are new products or should be removed:

- Ready To Cook category (6): Multigrain Millet Dosa Mix 180, Ragi Dosa Mix 180, Rava Dosa Mix 180, Rava Uppma Mix 180, Rice Uppuma Mix 120, Wheat Rava Uppma Mix 180
- Tomato Vathal 75 (category "Vegetable Vathal")
- Millets Laddus not on live: Navadhanya Laddu (5), Pachai Payaru Laddu (5), Ragi Laddu (5), Thinai Laddu (5), all 80

---

## TASK 7: Category structure

Live uses extra categories. Either add them or keep the current structure after owner approval.

- Live Thokku has 12 items (most are also in Pickles). The build has only 1. Option: also list in Thokku every Pickles item whose name contains "Thokku" or "Thuvaiyal", or leave as is.
- Live sub-categories under Pakshanams: Murukku, Mixture, Chips, Thattai. Under Sweets: Halwa. Under Podi: Kitchen Podis, Rice Mix Podi, Rice Mix Herbal Podi. Under Pickles: Rasam Paste, Rice Mix Paste.
- Live also has an "Always loved by everyone" featured collection (Pirandai Podi, Karuppu Ellu Idly Podi, Vathakuzambu Paste, Pirandai Thuvaiyal, Mudakkathan Thokku, Mysore Rasam Podi, Spl Health Mix, Karuppu Kavuni Kanji Mix). Use it to feed the "Popular in the shop" section on the homepage.

---

## TASK 8: Daily menu (check against the same date)

The daily menu is date-specific. On 31 Oct 2026 live showed these dishes, which the build menu does not show. Add them to the daily menu admin and compare again for the same date.

- **Breakfast (7:30 to 9:30 AM):** Idly with Vadai 110, Idly (4) 110, Poori (2) 110, Plain Dosa (2) 110, Ghee Pongal 110, Rasa Vadai (1) 70, Sambar Vadai (1) 70, Ghee Podi Dosa (2) 130, Vadai (1) 25, Sambar Idly (2) 80, Ghee Dosa (2) 120
- **Lunch:** Full meals with rice 210, Full meals without rice 160, Spl Bisibelabath 150, and single packs at 50 each: Tomato Rasam, Chow Chow Kootu, Morekuzhambu, Kose Poriyal
- **Dinner:** Kancheepuram Idly (2) 130, Poori (2) 110, Idiyappam (4) 110, Chapathi (1) 110, Onion Chennai Masala 80, Only Chapathi 15, Pasiparuppu Dhall 60

Build-only daily dishes to confirm with the owner: Kariveppilai Sadam 100, Carrot Poriyal 50, Vendaikkai Vathakuzambu 50, Rice Uppuma 110, Idly (4) as dinner 110.

---

## Acceptance checks

1. Every in-stock live product in Task 1 and Task 2 exists in the build and can be added to cart.
2. Task 3 prices match live.
3. Out-of-stock items cannot be added to cart.
4. The Diwali banner button opens a page that lists the Diwali products.
5. Re-run a comparison against https://www.annamfood.in and confirm the difference list is empty, apart from Task 6 items.
