(function (wp) {
  const el = wp.element.createElement;
  const { registerBlockType } = wp.blocks;
  const { InspectorControls, MediaUpload, MediaUploadCheck, useBlockProps } = wp.blockEditor;
  const { PanelBody, TextControl, Button, Notice } = wp.components;
  const labels = { hero: 'Campaign slider', promotions: 'Promotion tiles', categories: 'Food categories', 'daily-menu': 'Daily meals', delivery: 'Delivery checker', announcement: 'Announcement', contact: 'Store contact details' };
  Object.entries(labels).forEach(([name, title]) => registerBlockType('seerkitchen/' + name, {
    apiVersion: 3, title, icon: name === 'hero' ? 'images-alt2' : 'store', category: 'design',
    attributes: { items: { type: 'array', default: [] }, title: { type: 'string', default: '' } },
    supports: { align: ['wide', 'full'], html: false },
    edit: function ({ attributes, setAttributes }) {
      const items = attributes.items || [];
      const update = (index, field, value) => setAttributes({ items: items.map((item, i) => i === index ? { ...item, [field]: value } : item) });
      const media = (item, index, field, label) => el(MediaUploadCheck, {}, el(MediaUpload, {
        allowedTypes: ['image'], value: item[field] || 0,
        onSelect: image => { update(index, field, image.id); updateImage(index, field, image); },
        render: ({ open }) => el(Button, { variant: 'secondary', onClick: open }, label)
      }));
      // Store IDs as the authority, URLs only as editor previews.
      const updateImage = (index, field, image) => setAttributes({ items: items.map((item, i) => i === index ? { ...item, [field]: image.id, [field + 'Preview']: image.url, alt: item.alt || image.alt || image.title } : item) });
      const editableImages = ['hero', 'promotions'].includes(name);
      const settings = editableImages ? items.map((item, index) => el(PanelBody, { title: 'Image ' + (index + 1), initialOpen: index === 0, key: index },
        media(item, index, 'image', 'Choose desktop image'),
        name === 'hero' && media(item, index, 'mobile', 'Choose mobile image'),
        el(TextControl, { label: 'Image description', value: item.alt || '', onChange: value => update(index, 'alt', value) }),
        el(TextControl, { label: 'Destination URL', value: item.url || '', onChange: value => update(index, 'url', value) }),
        el(TextControl, { label: 'Start date (optional)', type: 'date', value: item.start || '', onChange: value => update(index, 'start', value) }),
        el(TextControl, { label: 'End date (optional)', type: 'date', value: item.end || '', onChange: value => update(index, 'end', value) }),
        el(Button, { variant: 'tertiary', disabled: index === 0, onClick: () => { const next = [...items]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; setAttributes({ items: next }); } }, 'Move earlier'),
        el(Button, { isDestructive: true, onClick: () => setAttributes({ items: items.filter((_, i) => i !== index) }) }, 'Remove image')
      )) : [el(PanelBody, { title: 'Content', key: 'content' },
        el(TextControl, { label: 'Section heading', value: attributes.title || '', onChange: title => setAttributes({ title }) }),
        el('p', {}, name === 'announcement' ? 'Change the announcement in Kitchen → Kitchen settings.' : 'Live content comes from this store’s products, categories and kitchen settings.')
      )];
      return el(wp.element.Fragment, {},
        el(InspectorControls, {}, settings,
          editableImages && items.length < 3 && el(Button, { variant: 'primary', onClick: () => setAttributes({ items: [...items, { image: 0, mobile: 0, alt: '', url: '' }] }) }, 'Add image')),
        el('div', useBlockProps({ className: 'seer-editor-preview' }),
          el('strong', {}, title),
          editableImages && el('div', { style: { display: 'flex', gap: '8px', marginTop: '12px' } }, items.map((item, i) => item.imagePreview ? el('img', { key: i, src: item.imagePreview, alt: item.alt || '', style: { width: name === 'hero' ? '100%' : '30%', maxHeight: '260px', objectFit: 'cover' } }) : el('p', { key: i }, 'Choose image ' + (i + 1) + ' in the sidebar.'))),
          editableImages && !items.length && el(Notice, { status: 'info', isDismissible: false }, 'Add up to three images in the block sidebar. The slider contains artwork only.'),
          !editableImages && el('p', {}, attributes.title || 'This section displays your store’s live content.')
        )
      );
    },
    save: () => null
  }));
})(window.wp);
