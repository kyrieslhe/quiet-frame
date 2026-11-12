'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [c]));
const pad = n => String(n).padStart(2, '0');
const fields = ['title', 'location', 'taken_at', 'camera', 'lens', 'focal_length', 'aperture', 'shutter', 'iso', 'latitude', 'longitude', 'notes'];
let albums = [],
    token = '',
    currentPhoto = null,
    editingAlbum = null,
    toastTimer, busy = false,
    confirmation = null;
let homeView = localStorage.getItem('quiet-frame-view') || 'gallery';
let photoView = localStorage.getItem('quiet-frame-photo-view') || 'grid';

function toast(message, duration = 4000) {
    clearTimeout(toastTimer);
    $('#toast').textContent = message;
    $('#toast').classList.add('show');
    toastTimer = setTimeout(() => $('#toast').classList.remove('show'), duration);
}
async function api(path, options = {}) {
    const headers = {
        'X-Archive-Token': token,
        'Accept-Language': lang,
        ...options.headers
    };
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {
        ...options,
        headers
    });
    const json = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(json.error || `${t('requestError')} (${response.status})`);
    return json;
}

function albumId() {
    return location.hash.startsWith('#album/') ? location.hash.slice(7) : null;
}

function currentAlbum() {
    return albums.find(a => a.id === albumId());
}

function image(p, eager = false) {
    return `<img src="/media/${p.id}" alt="${esc(p.title)}" loading="${eager?'eager':'lazy'}">`;
}

function dateLabel(date) {
    return date ? esc(date.slice(0, 10).replaceAll('-', '.')) : t('noDate');
}
async function reload() {
    albums = await api('/api/albums');
    render();
}

function render() {
    const count = albums.reduce((n, a) => n + a.photos.length, 0);
    $('#nav-count').textContent = pad(albums.length);
    $('#footer-count').textContent = `${pad(albums.length)} ${t('collections')} / ${pad(count)} ${t('photographs')}`;
    $('#series-nav').innerHTML = albums.map((a, i) => `<a href="#album/${a.id}" ${albumId()===a.id?'aria-current="page"':''}><span class="series-number">${pad(i+1)}</span><span>${esc(a.title)}</span></a>`).join('');
    $('#home-link').classList.toggle('active', !albumId());
    const a = currentAlbum();
    if (albumId() && a) renderAlbum(a);
    else {
        if (albumId()) location.hash = '';
        renderHome();
    }
}

function switcher(items, selected, id) {
    return `<div class="view-switch" id="${id}">${items.map(([key,label])=>`<button data-view="${key}" aria-pressed="${selected===key}">${t(label)}</button>`).join('')}</div>`;
}

function renderHome() {
    $('#main').innerHTML = `<div class="page-top"><h1>${t('works')}<sup>${pad(albums.length)}</sup></h1><button class="text-button add-button" id="new-album">${t('newAlbum')} <span>＋</span></button></div>${albums.length?`<div class="toolbar"><input type="search" class="search" id="search" placeholder="${t('search')}" aria-label="${t('search')}">${switcher([['gallery','gallery'],['index','index']],homeView,'home-view')}</div><section id="collections" class="collection-grid ${homeView==='index'?'index-view':''}"></section>`:`<section class="welcome"><figure><img src="/static/demo/landscape.jpg" alt="${t('example')}" fetchpriority="high"><figcaption><span>${t('example')}</span><a href="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b" target="_blank" rel="noreferrer">Unsplash ↗</a></figcaption></figure><div class="welcome-caption"><div><h2>${t('firstTitle')}</h2><p>${t('firstText')}</p></div><button class="primary" id="first-album">${t('firstAction')} <span>↗</span></button></div><p class="welcome-note">${t('exampleNote')}</p></section>`}`;
    $('#new-album').onclick = () => openAlbumForm();
    if ($('#first-album')) $('#first-album').onclick = () => openAlbumForm();
    if ($('#search')) {
        $('#search').oninput = e => drawAlbums(e.target.value);
        $('#home-view').onclick = e => {
            const button = e.target.closest('[data-view]');
            if (!button) return;
            homeView = button.dataset.view;
            localStorage.setItem('quiet-frame-view', homeView);
            const query = $('#search').value;
            renderHome();
            $('#search').value = query;
            drawAlbums(query);
        };
        drawAlbums('');
    }
}

function drawAlbums(query) {
    const shown = albums.filter(a => (a.title + ' ' + a.location + ' ' + a.description).toLowerCase().includes(query.toLowerCase()));
    $('#collections').innerHTML = shown.length ? shown.map(a => {
        const number = pad(albums.indexOf(a) + 1);
        return `<a class="album-card" href="#album/${a.id}"><div class="album-image">${a.photos.length?image(a.photos[0],albums.indexOf(a)===0):`<div class="empty-cover"><span>＋</span><span>${t('noCover')}</span></div>`}</div><div class="album-meta"><span class="album-number">${number}</span><div class="album-name"><h2>${esc(a.title)}</h2><span>${esc(a.location)||t('noLocation')}</span></div><div class="album-date"><span>${dateLabel(a.date)}</span><span>${a.photos.length} ${t('photographs')}</span></div><span class="album-go">↗</span></div></a>`;
    }).join('') : `<p class="no-results">${t('noResults')}</p>`;
}

function renderAlbum(a) {
    $('#main').innerHTML = `<div class="breadcrumb"><a href="#">${t('works')}</a><span>/</span><span>${pad(albums.indexOf(a)+1)}</span></div><section class="album-intro"><div><h1>${esc(a.title)}</h1>${a.description?`<p class="album-description">${esc(a.description)}</p>`:''}</div><div class="album-facts"><span>${esc(a.location)||t('noLocation')}</span><span>${dateLabel(a.date)}</span><span>${a.photos.length} ${t('photographs')}</span></div></section><div class="toolbar album-toolbar"><div class="album-controls"><button class="text-button" id="edit-album">${t('editAlbum')}</button><button class="text-button add-button" id="add-photos">${t('import')} <span>＋</span></button></div>${switcher([['grid','grid'],['sequence','sequence']],photoView,'photo-view')}</div><div class="import-status" id="import-status" aria-live="polite">${t('drop')}</div><section id="drop-zone" class="drop-zone">${a.photos.length?`<div class="photo-grid ${photoView==='sequence'?'sequence-view':''}">${a.photos.map((p,i)=>`<button class="photo-card" data-photo="${p.id}">${image(p,i===0)}<div class="photo-caption"><span class="photo-number">${pad(i+1)}</span><span>${esc(p.title)}</span><span class="photo-settings">${esc(p.focal_length)} ${esc(p.aperture)}</span></div></button>`).join('')}</div>`:`<div class="empty"><span class="empty-plus">＋</span><h2>${t('photoEmpty')}</h2><p>${t('photoEmptyText')}</p><button class="primary" id="empty-import">${t('choose')} <span>↗</span></button><small>${t('formats')}</small></div>`}</section><div class="album-bottom"><span>${t('formats')}</span><button class="text-button danger" id="delete-album">${t('deleteAlbum')}</button></div>`;
    $('#edit-album').onclick = () => openAlbumForm(a);
    $('#add-photos').onclick = choosePhotos;
    if ($('#empty-import')) $('#empty-import').onclick = choosePhotos;
    $('#photo-view').onclick = e => {
        const button = e.target.closest('[data-view]');
        if (!button) return;
        photoView = button.dataset.view;
        localStorage.setItem('quiet-frame-photo-view', photoView);
        renderAlbum(a);
    };
    document.querySelectorAll('[data-photo]').forEach(b => b.onclick = () => openPhoto(b.dataset.photo));
    $('#delete-album').onclick = () => confirmAction('deleteAlbumTitle', 'deleteAlbumCopy', {
        title: a.title,
        count: a.photos.length
    }, async () => {
        await api(`/api/albums/${a.id}`, {
            method: 'DELETE'
        });
        location.hash = '';
        await reload();
        toast(t('albumDeleted'));
    });
    const zone = $('#main');
    zone.ondragover = e => {
        if (e.dataTransfer.types.includes('Files')) {
            e.preventDefault();
            $('#drop-zone')?.classList.add('dragging');
        }
    };
    zone.ondragleave = e => {
        if (!zone.contains(e.relatedTarget)) $('#drop-zone')?.classList.remove('dragging');
    };
    zone.ondrop = e => {
        e.preventDefault();
        $('#drop-zone')?.classList.remove('dragging');
        importPhotos(e.dataTransfer.files);
    };
}

function openAlbumForm(album = null) {
    editingAlbum = album;
    $('#album-form').reset();
    $('#album-form-heading').textContent = t(album ? 'editAlbum' : 'newAlbum');
    if (album)
        for (const key of ['title', 'location', 'description', 'date']) $('#album-form').elements[key].value = album[key];
    $('#album-dialog').showModal();
}
$('#album-form').onsubmit = async e => {
    e.preventDefault();
    const button = e.submitter;
    button.disabled = true;
    try {
        const body = Object.fromEntries(new FormData(e.target));
        const result = await api(editingAlbum ? `/api/albums/${editingAlbum.id}` : '/api/albums', {
            method: editingAlbum ? 'PATCH' : 'POST',
            body: JSON.stringify(body)
        });
        $('#album-dialog').close();
        await reload();
        if (!editingAlbum) location.hash = `album/${result.id}`;
        toast(t('albumSaved'));
    } catch (err) {
        toast(err.message);
    } finally {
        button.disabled = false;
    }
};

function choosePhotos() {
    if (!busy) $('#file-input').click();
}
$('#file-input').onchange = e => {
    importPhotos(e.target.files);
    e.target.value = '';
};
async function importPhotos(files) {
    const a = currentAlbum();
    if (!a || !files.length || busy) return;
    const list = Array.from(files);
    if (list.reduce((s, f) => s + f.size, 0) > 512 * 1024 * 1024) {
        toast(t('limit'));
        return;
    }
    busy = true;
    if ($('#import-status')) $('#import-status').textContent = t('importing', {
        count: list.length
    });
    toast(t('importing', {
        count: list.length
    }), 60000);
    const data = new FormData();
    list.forEach(f => data.append('photos', f));
    try {
        const result = await api(`/api/albums/${a.id}/photos`, {
            method: 'POST',
            body: data
        });
        await reload();
        toast(t('imported', {
            count: result.added.length
        }) + (result.errors.length ? '\n' + result.errors.map(x => x.filename + ': ' + x.error).join('\n') : ''), result.errors.length ? 15000 : 4000);
    } catch (err) {
        toast(err.message, 10000);
    } finally {
        busy = false;
        if ($('#import-status')) $('#import-status').textContent = t('drop');
    }
}

function openPhoto(id) {
    const a = currentAlbum();
    const p = a?.photos.find(p => p.id === id);
    if (!p) return;
    currentPhoto = p;
    $('#large-photo').src = `/media/${id}`;
    $('#large-photo').alt = p.title;
    $('#photo-heading').textContent = p.title;
    $('#photo-counter').textContent = `${pad(a.photos.indexOf(p)+1)} / ${pad(a.photos.length)}`;
    $('#photo-read').innerHTML = `<dl class="metadata">${fields.filter(k=>k!=='title'&&k!=='notes').map(k=>`<div class="metadata-row"><dt>${t(k)}</dt><dd>${esc(k==='taken_at'?p[k]?.replace('T',' '):p[k])||'—'}</dd></div>`).join('')}</dl>${p.notes?`<p class="notes">${esc(p.notes)}</p>`:''}`;
    $('#download-original').href = `/media/${id}?original=1`;
    $('#photo-form').hidden = true;
    $('#photo-read').hidden = false;
    $('#photo-actions').hidden = false;
    if (!$('#photo-dialog').open) $('#photo-dialog').showModal();
}
$('#edit-photo').onclick = () => {
    const p = currentPhoto;
    $('#photo-form').innerHTML = fields.map(k => `<label><span data-i18n="${k}">${t(k)}</span>${k==='notes'?`<textarea name="${k}" rows="3">${esc(p[k])}</textarea>`:`<input name="${k}" value="${esc(p[k])}" ${k==='title'?'required':''}>`}</label>`).join('') + `<button class="primary" type="submit" data-i18n="save">${t('save')}</button><button type="button" class="text-button cancel-edit" id="cancel-edit" data-i18n="cancelEdit">${t('cancelEdit')}</button>`;
    $('#photo-read').hidden = true;
    $('#photo-actions').hidden = true;
    $('#photo-form').hidden = false;
    $('#cancel-edit').onclick = () => openPhoto(p.id);
};
$('#photo-form').onsubmit = async e => {
    e.preventDefault();
    const button = e.submitter;
    button.disabled = true;
    try {
        const id = currentPhoto.id;
        await api(`/api/photos/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(Object.fromEntries(new FormData(e.target)))
        });
        await reload();
        openPhoto(id);
        toast(t('photoSaved'));
    } catch (err) {
        toast(err.message);
    } finally {
        button.disabled = false;
    }
};

function stepPhoto(direction) {
    if (!$('#photo-form').hidden) return;
    const photos = currentAlbum()?.photos || [];
    const index = photos.findIndex(p => p.id === currentPhoto?.id);
    if (photos.length) openPhoto(photos[(index + direction + photos.length) % photos.length].id);
}
$('#prev').onclick = () => stepPhoto(-1);
$('#next').onclick = () => stepPhoto(1);
document.addEventListener('keydown', e => {
    if ($('#photo-dialog').open && !$('#confirm-dialog').open && !/INPUT|TEXTAREA/.test(e.target.tagName)) {
        if (e.key === 'ArrowLeft') stepPhoto(-1);
        if (e.key === 'ArrowRight') stepPhoto(1);
    }
});
$('#set-cover').onclick = async () => {
    try {
        await api(`/api/photos/${currentPhoto.id}/cover`, {
            method: 'POST'
        });
        await reload();
        openPhoto(currentPhoto.id);
        toast(t('coverSaved'));
    } catch (err) {
        toast(err.message);
    }
};
$('#delete-photo').onclick = () => {
    const id = currentPhoto.id;
    confirmAction('deletePhotoTitle', 'deletePhotoCopy', {}, async () => {
        await api(`/api/photos/${id}`, {
            method: 'DELETE'
        });
        $('#photo-dialog').close();
        await reload();
        toast(t('photoDeleted'));
    });
};

function updateConfirmation() {
    if (confirmation) {
        $('#confirm-title').textContent = t(confirmation.title);
        $('#confirm-copy').textContent = t(confirmation.copy, confirmation.values);
    }
}

function confirmAction(title, copy, values, callback) {
    confirmation = {
        title,
        copy,
        values
    };
    updateConfirmation();
    $('#confirm-dialog').showModal();
    $('#confirm-ok').onclick = async () => {
        const button = $('#confirm-ok');
        button.disabled = true;
        try {
            await callback();
            $('#confirm-dialog').close();
        } catch (err) {
            toast(err.message);
        } finally {
            button.disabled = false;
        }
    };
}

function setLanguage(code) {
    lang = code;
    localStorage.setItem('quiet-frame-language', lang);
    localize();
    const query = $('#search')?.value;
    render();
    if (query && $('#search')) {
        $('#search').value = query;
        drawAlbums(query);
    }
    if ($('#photo-dialog').open && $('#photo-form').hidden) openPhoto(currentPhoto.id);
    if ($('#album-dialog').open) $('#album-form-heading').textContent = t(editingAlbum ? 'editAlbum' : 'newAlbum');
    if ($('#confirm-dialog').open) updateConfirmation();
    $('#toast').classList.remove('show');
}
$('#lang-zh').onclick = () => setLanguage('zh');
$('#lang-en').onclick = () => setLanguage('en');
$('#confirm-cancel').onclick = () => $('#confirm-dialog').close();
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());
$('#about-button').onclick = () => $('#about-dialog').showModal();
window.addEventListener('hashchange', () => {
    if ($('#photo-dialog').open) $('#photo-dialog').close();
    $('#main').ondragover = null;
    $('#main').ondrop = null;
    render();
    window.scrollTo(0, 0);
});
localize();
(async () => {
    try {
        token = (await api('/api/session')).token;
        await reload();
    } catch (err) {
        $('#main').textContent = t('connectingError');
        toast(err.message);
    }
})();

// A saved choice overrides the system; otherwise keep following the OS setting.
function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme)));
}
document.querySelectorAll('[data-theme-choice]').forEach(button => button.onclick = () => {
    localStorage.setItem('quiet-frame-theme', button.dataset.themeChoice);
    applyTheme(button.dataset.themeChoice);
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
    if (!localStorage.getItem('quiet-frame-theme')) applyTheme(event.matches ? 'dark' : 'light');
});
applyTheme(document.documentElement.dataset.theme);
