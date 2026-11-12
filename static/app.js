'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [c]));
const fields = ['title', 'location', 'taken_at', 'camera', 'lens', 'focal_length', 'aperture', 'shutter', 'iso', 'latitude', 'longitude', 'notes'];
let albums = [],
    token = '',
    currentPhoto = null,
    selectedId = null,
    editingAlbum = null,
    confirmation = null,
    busy = false,
    toastTimer;
let photoView = localStorage.getItem('quiet-frame-photo-view') === 'list' ? 'list' : 'grid';
let query = '',
    sort = 'position';
let thumbSize = Number(localStorage.getItem('quiet-frame-thumb-size')) || 220;

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
    if (options.body) headers['Content-Type'] = 'application/json';
    const r = await fetch(path, {
        ...options,
        headers
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || `${t('requestError')} (${r.status})`);
    return body;
}

function albumId() {
    return location.hash.startsWith('#album/') ? location.hash.slice(7) : null;
}

function currentAlbum() {
    return albums.find(a => a.id === albumId());
}

function allPhotos() {
    return albums.flatMap(a => a.photos.map(p => ({
        ...p,
        album_title: a.title
    })));
}

function getPhoto(id) {
    return allPhotos().find(p => p.id === id);
}

function visiblePhotos() {
    const a = currentAlbum();
    let photos = a ? a.photos : allPhotos();
    photos = photos.filter(p => (p.title + ' ' + p.location + ' ' + p.camera + ' ' + p.source_path).toLowerCase().includes(query.toLowerCase()));
    if (sort === 'title') photos = [...photos].sort((a, b) => a.title.localeCompare(b.title));
    if (sort === 'date') photos = [...photos].sort((a, b) => (b.taken_at || '').localeCompare(a.taken_at || ''));
    return photos;
}

function preview(p) {
    return `/media/${p.id}?v=${p.preview_version}`;
}
async function reload() {
    albums = await api('/api/albums');
    render();
}

function render() {
    if (albumId() && !currentAlbum()) {
        location.hash = '';
        return;
    }
    const a = currentAlbum(),
        photos = allPhotos();
    $('#nav-count').textContent = photos.length;
    $('#home-link').classList.toggle('active', !a);
    $('#series-nav').innerHTML = albums.map(a => `<a class="nav-item ${albumId()===a.id?'active':''}" href="#album/${a.id}"><span class="nav-symbol">▤</span><span class="series-title">${esc(a.title)}</span><span class="nav-count">${a.photos.length}</span></a>`).join('');
    $('#main').innerHTML = `<div class="workspace-heading"><div><h1>${a?esc(a.title):t('allPhotos')}</h1><span>${a?esc(a.location)||t('collection'):t('library')}</span></div><div class="heading-actions"><button class="icon-button" id="refresh" title="${t('refresh')}" aria-label="${t('refresh')}">↻</button>${a?`<button class="outline" id="edit-album">${t('editAlbum')}</button>`:''}<button class="primary" id="add-photos">＋ ${t('import')}</button></div></div><div class="workspace-toolbar"><input class="search" id="search" type="search" placeholder="${t('search')}" aria-label="${t('search')}" value="${esc(query)}"><div class="view-switch"><button data-view="grid" aria-pressed="${photoView==='grid'}" title="${t('grid')}">▦</button><button data-view="list" aria-pressed="${photoView==='list'}" title="${t('index')}">☷</button></div><input class="size-slider" id="thumb-size" aria-label="${t('thumbnailSize')}" type="range" min="150" max="340" value="${thumbSize}"></div><div class="photo-workspace" id="photo-workspace"></div>${a?`<div class="collection-actions"><span>${esc(a.description)}</span><button class="text-button danger" id="delete-album">${t('deleteAlbum')}</button></div>`:''}`;
    $('#add-photos').onclick = () => openImport();
    $('#refresh').onclick = () => reload().catch(e => toast(e.message));
    if (a) {
        $('#edit-album').onclick = () => openAlbumForm(a);
        $('#delete-album').onclick = () => confirmAction('deleteAlbumTitle', 'deleteAlbumCopy', {
            title: a.title,
            count: a.photos.length
        }, async () => {
            await api(`/api/albums/${a.id}`, {
                method: 'DELETE'
            });
            selectedId = null;
            location.hash = '';
            await reload();
            toast(t('albumDeleted'));
        });
    }
    $('#search').oninput = e => {
        query = e.target.value;
        drawPhotos();
    };
    document.querySelectorAll('[data-view]').forEach(b => b.onclick = () => {
        photoView = b.dataset.view;
        localStorage.setItem('quiet-frame-photo-view', photoView);
        render();
    });
    $('#thumb-size').oninput = e => {
        thumbSize = Number(e.target.value);
        localStorage.setItem('quiet-frame-thumb-size', thumbSize);
        $('#photo-workspace').style.setProperty('--thumb-size', thumbSize + 'px');
    };
    drawPhotos();
    drawInspector();
}

function drawPhotos() {
    const photos = visiblePhotos(),
        all = allPhotos(),
        workspace = $('#photo-workspace');
    workspace.style.setProperty('--thumb-size', thumbSize + 'px');
    const missing = photos.filter(p => !p.source_exists).length;
    $('#footer-count').textContent = `${photos.length} ${t('photographs')}${selectedId?' · '+t('selectionCount'):''}`;
    $('#app-status').textContent = missing ? t('missingCount', {
        count: missing
    }) : t('referenceMode');
    workspace.innerHTML = photos.length ? `<div class="photo-grid ${photoView==='list'?'list-view':''}">${photos.map(p=>`<button class="photo-card ${selectedId===p.id?'selected':''}" data-photo="${p.id}" aria-pressed="${selectedId===p.id}"><div class="thumbnail"><img src="${preview(p)}" alt="${esc(p.title)}" loading="lazy">${!p.source_exists?`<span class="offline-badge" title="${t('offline')}">!</span>`:''}</div><div class="photo-caption"><strong>${esc(p.title)}</strong><span>${esc(p.location)||esc(p.camera)||'—'}</span><span class="list-parameter">${esc(p.aperture)} ${esc(p.shutter)} ${p.iso?'ISO '+esc(p.iso):''}</span></div></button>`).join('')}</div>` : all.length && query ? `<div class="empty-state"><h2>${t('noResults')}</h2></div>` : `<div class="empty-state"><div class="folder-illustration"><span>＋</span></div><h2>${t('emptyLibrary')}</h2><p>${t('emptyLibraryHelp')}</p><button class="primary" id="empty-import">${t('addPhotos')}</button><small>JPG · PNG · WEBP · TIFF</small></div>`;
    if ($('#empty-import')) $('#empty-import').onclick = () => openImport();
    document.querySelectorAll('[data-photo]').forEach(b => {
        b.onclick = () => selectPhoto(b.dataset.photo);
        b.ondblclick = () => openPhoto(b.dataset.photo);
    });
}

function selectPhoto(id) {
    selectedId = id;
    currentPhoto = getPhoto(id);
    document.querySelectorAll('[data-photo]').forEach(b => {
        b.classList.toggle('selected', b.dataset.photo === id);
        b.setAttribute('aria-pressed', String(b.dataset.photo === id));
    });
    $('#footer-count').textContent = visiblePhotos().length + ' ' + t('photographs') + ' · ' + t('selectionCount');
    drawInspector();
}

function metadataHtml(p) {
    return `<div class="source-status ${p.source_exists?'':'offline'}"><i></i>${t(p.source_exists?'online':'offline')}</div>${!p.source_exists?`<p class="offline-note">${t('offlineHelp')}</p>`:''}<div class="source-path"><span>${t('sourcePath')}</span><code>${esc(p.source_path)}</code></div><dl class="metadata">${fields.filter(k=>k!=='title'&&k!=='notes').map(k=>`<div class="metadata-row"><dt>${t(k)}</dt><dd>${esc(k==='taken_at'?p[k]?.replace('T',' '):p[k])||'—'}</dd></div>`).join('')}</dl>${p.notes?`<p class="notes">${esc(p.notes)}</p>`:''}`;
}

function drawInspector() {
    const p = getPhoto(selectedId);
    if (!p) {
        $('#inspector').innerHTML = `<div class="inspector-heading">${t('photoDetails')}</div><div class="inspector-empty"><span>ⓘ</span><h2>${t('noSelection')}</h2><p>${t('selectHelp')}</p></div>`;
        return;
    }
    $('#inspector').innerHTML = `<div class="inspector-heading">${t('photoDetails')}<button class="icon-button" id="inspector-open" title="${t('viewLarge')}" aria-label="${t('viewLarge')}">⤢</button></div><div class="inspector-scroll"><img class="inspector-preview" src="${preview(p)}" alt="${esc(p.title)}"><h2>${esc(p.title)}</h2>${metadataHtml(p)}<div class="inspector-actions"><button class="outline" id="inspector-edit">${t('editPhoto')}</button><button class="text-button" id="inspector-reveal" ${p.source_exists?'':'disabled'}>${t('reveal')}</button><button class="text-button" id="inspector-relink">${t('relink')}</button></div></div>`;
    $('#inspector-open').onclick = () => openPhoto(p.id);
    $('#inspector-edit').onclick = () => {
        openPhoto(p.id);
        $('#edit-photo').click();
    };
    $('#inspector-reveal').onclick = () => reveal(p.id);
    $('#inspector-relink').onclick = () => openRelink(p.id);
}

function openAlbumForm(album = null) {
    editingAlbum = album;
    $('#album-form').reset();
    $('#album-form-heading').textContent = t(album ? 'editAlbum' : 'newAlbum');
    if (album)
        for (const k of ['title', 'location', 'description', 'date']) $('#album-form').elements[k].value = album[k];
    $('#album-dialog').showModal();
}
$('#new-album').onclick = () => openAlbumForm();
$('#home-link').onclick = () => {
    location.hash = '';
    selectedId = null;
    query = '';
    render();
};
$('#album-form').onsubmit = async e => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
        const result = await api(editingAlbum ? `/api/albums/${editingAlbum.id}` : '/api/albums', {
            method: editingAlbum ? 'PATCH' : 'POST',
            body: JSON.stringify(Object.fromEntries(new FormData(e.target)))
        });
        $('#album-dialog').close();
        await reload();
        if (!editingAlbum) location.hash = `album/${result.id}`;
        toast(t('albumSaved'));
    } catch (e) {
        toast(e.message);
    } finally {
        b.disabled = false;
    }
};

function openImport() {
    if (busy) return;
    $('#path-input').value = '';
    $('#import-progress').textContent = '';
    $('#import-errors').textContent = '';
    $('#import-dialog').showModal();
}

function nativeApi() {
    return window.pywebview?.api;
}
async function choosePhotos() {
    const bridge = nativeApi();
    if (!bridge) {
        toast(t('nativeRequired'));
        $('#import-dialog details').open = true;
        return;
    }
    try {
        const paths = await bridge.choose_files(true);
        if (paths.length) await importPaths(paths);
    } catch (e) {
        toast(e.message);
    }
}
$('#pick-files').onclick = choosePhotos;
$('#pick-folder').onclick = async () => {
    const bridge = nativeApi();
    if (!bridge) {
        toast(t('nativeRequired'));
        return;
    }
    try {
        const selected = await bridge.choose_folder();
        if (!selected.length) return;
        const result = await api('/api/folders/scan', {
            method: 'POST',
            body: JSON.stringify({
                path: selected[0],
                recursive: $('#recursive').checked
            })
        });
        if (!result.paths.length) {
            toast(t('noFiles'));
            return;
        }
        await importPaths(result.paths, result.folder_name);
    } catch (e) {
        toast(e.message, 10000);
    }
};

function parsePaths(text) {
    return text.split(/\r?\n/).map(s => s.trim().replace(/^["']|["']$/g, '')).filter(Boolean).map(s => s.startsWith('file://') ? decodeURIComponent(new URL(s).pathname) : s);
}
$('#add-paths').onclick = () => importPaths(parsePaths($('#path-input').value));
async function importPaths(paths, albumName = '') {
    if (!paths.length || busy) return;
    busy = true;
    let added = 0,
        skipped = 0,
        errors = [];
    document.querySelectorAll('#import-dialog button:not([data-close])').forEach(b => b.disabled = true);
    try {
        let a = currentAlbum();
        if (!a) {
            const result = await api('/api/albums', {
                method: 'POST',
                body: JSON.stringify({
                    title: albumName || t('newCollectionDefault') + ' ' + new Date().toLocaleDateString()
                })
            });
            a = {
                id: result.id
            };
        }
        for (let i = 0; i < paths.length; i += 100) {
            $('#import-progress').textContent = `${t('importing',{count:paths.length})} ${i} / ${paths.length}`;
            const result = await api(`/api/albums/${a.id}/photos`, {
                method: 'POST',
                body: JSON.stringify({
                    paths: paths.slice(i, i + 100)
                })
            });
            added += result.added.length;
            skipped += result.skipped.length;
            errors.push(...result.errors);
        }
        await reload();
        location.hash = `album/${a.id}`;
        $('#import-progress').textContent = t('added', {
            count: added,
            skipped
        });
        $('#import-errors').textContent = errors.map(e => `${e.filename}: ${e.error}`).join('\n');
        if (!errors.length) {
            $('#import-dialog').close();
            toast(t('added', {
                count: added,
                skipped
            }));
        }
    } catch (e) {
        $('#import-errors').textContent = e.message;
    } finally {
        busy = false;
        document.querySelectorAll('#import-dialog button').forEach(b => b.disabled = false);
    }
}

function openPhoto(id) {
    const p = getPhoto(id);
    if (!p) return;
    selectedId = id;
    currentPhoto = p;
    drawPhotos();
    drawInspector();
    $('#large-photo').src = preview(p);
    $('#large-photo').alt = p.title;
    $('#photo-heading').textContent = p.title;
    const photos = visiblePhotos();
    $('#photo-counter').textContent = `${photos.findIndex(p=>p.id===id)+1} / ${photos.length}`;
    $('#photo-read').innerHTML = metadataHtml(p);
    $('#photo-form').hidden = true;
    $('#photo-read').hidden = false;
    $('#photo-actions').hidden = false;
    $('#reveal-photo').disabled = !p.source_exists;
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
    const b = e.submitter;
    b.disabled = true;
    try {
        const id = currentPhoto.id;
        await api(`/api/photos/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(Object.fromEntries(new FormData(e.target)))
        });
        await reload();
        openPhoto(id);
        toast(t('photoSaved'));
    } catch (e) {
        toast(e.message);
    } finally {
        b.disabled = false;
    }
};
async function reveal(id) {
    const bridge = nativeApi();
    if (!bridge) {
        toast(t('nativeRequired'));
        return;
    }
    try {
        if (!(await bridge.reveal_source(id)).ok) toast(t('offlineHelp'));
    } catch (e) {
        toast(e.message);
    }
}
$('#reveal-photo').onclick = () => reveal(currentPhoto.id);
let relinkId = null;

function openRelink(id) {
    relinkId = id;
    $('#relink-path').value = getPhoto(id)?.source_path || '';
    $('#relink-dialog').showModal();
}
$('#relink-photo').onclick = () => openRelink(currentPhoto.id);
async function relinkPath(path) {
    try {
        await api(`/api/photos/${relinkId}/relink`, {
            method: 'POST',
            body: JSON.stringify({
                path
            })
        });
        $('#relink-dialog').close();
        await reload();
        if ($('#photo-dialog').open) openPhoto(relinkId);
        toast(t('relinked'));
    } catch (e) {
        toast(e.message, 10000);
    }
}
$('#save-relink').onclick = () => relinkPath($('#relink-path').value.trim());
$('#pick-relink').onclick = async () => {
    const bridge = nativeApi();
    if (!bridge) {
        toast(t('nativeRequired'));
        return;
    }
    const files = await bridge.choose_files(false);
    if (files.length) await relinkPath(files[0]);
};

function stepPhoto(direction) {
    if (!$('#photo-form').hidden) return;
    const photos = visiblePhotos(),
        i = photos.findIndex(p => p.id === currentPhoto?.id);
    if (photos.length) openPhoto(photos[(i + direction + photos.length) % photos.length].id);
}
$('#prev').onclick = () => stepPhoto(-1);
$('#next').onclick = () => stepPhoto(1);
$('#set-cover').onclick = async () => {
    try {
        await api(`/api/photos/${currentPhoto.id}/cover`, {
            method: 'POST'
        });
        await reload();
        openPhoto(currentPhoto.id);
        toast(t('coverSaved'));
    } catch (e) {
        toast(e.message);
    }
};

function removePhoto(id) {
    confirmAction('deletePhotoTitle', 'deletePhotoCopy', {}, async () => {
        await api(`/api/photos/${id}`, {
            method: 'DELETE'
        });
        if ($('#photo-dialog').open) $('#photo-dialog').close();
        selectedId = null;
        await reload();
        toast(t('photoDeleted'));
    });
}
$('#delete-photo').onclick = () => removePhoto(currentPhoto.id);

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
        const b = $('#confirm-ok');
        b.disabled = true;
        try {
            await callback();
            $('#confirm-dialog').close();
        } catch (e) {
            toast(e.message);
        } finally {
            b.disabled = false;
        }
    };
}
$('#confirm-cancel').onclick = () => $('#confirm-dialog').close();

function setLanguage(code) {
    lang = code;
    localStorage.setItem('quiet-frame-language', lang);
    localize();
    render();
    if ($('#photo-dialog').open && $('#photo-form').hidden) openPhoto(currentPhoto.id);
    if ($('#album-dialog').open) $('#album-form-heading').textContent = t(editingAlbum ? 'editAlbum' : 'newAlbum');
    if ($('#confirm-dialog').open) updateConfirmation();
    $('#toast').classList.remove('show');
}
$('#lang-zh').onclick = () => setLanguage('zh');
$('#lang-en').onclick = () => setLanguage('en');

function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('[data-theme-choice]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeChoice === theme)));
}
document.querySelectorAll('[data-theme-choice]').forEach(b => b.onclick = () => {
    localStorage.setItem('quiet-frame-theme', b.dataset.themeChoice);
    applyTheme(b.dataset.themeChoice);
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    if (!localStorage.getItem('quiet-frame-theme')) applyTheme(e.matches ? 'dark' : 'light');
});
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());
$('#about-button').onclick = () => $('#about-dialog').showModal();
$('#backup-button').onclick = async () => {
    try {
        if (nativeApi()) {
            const result = await nativeApi().export_catalog();
            if (result.ok) toast(t('savedCatalog'));
        } else {
            const link = document.createElement('a');
            link.href = '/api/backup';
            link.click();
        }
    } catch (e) {
        toast(e.message);
    }
};
$('#project-button').onclick = () => {
    if (nativeApi()) nativeApi().open_project();
    else window.open('https://github.com/kyrieslhe/quiet-frame', '_blank', 'noopener');
};
window.addEventListener('hashchange', () => {
    if ($('#photo-dialog').open) $('#photo-dialog').close();
    selectedId = null;
    query = '';
    render();
});
document.addEventListener('keydown', e => {
    if (/INPUT|TEXTAREA/.test(e.target.tagName)) return;
    const dialog = document.querySelector('dialog[open]');
    if ($('#photo-dialog').open && !$('#confirm-dialog').open && !$('#relink-dialog').open) {
        if (e.key === 'ArrowLeft') stepPhoto(-1);
        if (e.key === 'ArrowRight') stepPhoto(1);
        return;
    }
    if (dialog) return;
    if ((e.metaKey || e.ctrlKey) && e.key === 'o') {
        e.preventDefault();
        openImport();
    }
    if (e.key === 'Enter' && selectedId) openPhoto(selectedId);
    if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        e.preventDefault();
        removePhoto(selectedId);
    }
});
localize();
applyTheme(document.documentElement.dataset.theme);
(async () => {
    try {
        token = (await api('/api/session')).token;
        await reload();
    } catch (e) {
        $('#main').textContent = t('connectingError');
        toast(e.message);
    }
})();
