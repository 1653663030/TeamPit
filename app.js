// ================================================================
// 全局状态
// ================================================================
let state = {
    roomId: '',
    userId: '',
};

const API_BASE = '';

// ================================================================
// 工具函数
// ================================================================
function toFormData(data) {
    const form = new FormData();
    for (const key in data) {
        if (data[key] !== undefined && data[key] !== null && data[key] !== '') {
            form.append(key, data[key]);
        }
    }
    return form;
}

async function apiCall(url, method = 'GET', data = null) {
    const options = { method, headers: {} };
    if (data) {
        if (data instanceof FormData) {
            options.body = data;
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(data);
        }
    }
    const resp = await fetch(`${API_BASE}${url}`, options);
    const contentType = resp.headers.get('content-type');
    let responseData;
    if (contentType && contentType.includes('application/json')) {
        responseData = await resp.json();
    } else {
        responseData = await resp.text();
    }
    if (!resp.ok) {
        // 如果响应是 JSON，取 detail 字段；否则直接显示文本
        let errMsg;
        if (typeof responseData === 'object' && responseData.detail) {
            errMsg = responseData.detail;
        } else if (typeof responseData === 'string') {
            errMsg = responseData;
        } else {
            errMsg = `请求失败（状态码 ${resp.status}）`;
        }
        throw new Error(errMsg);
    }
    return responseData;
}

// ================================================================
// 页面切换
// ================================================================
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.add('d-none'));
    document.getElementById(pageId).classList.remove('d-none');
}

function goToDashboard(roomId, userId) {
    state.roomId = roomId;
    state.userId = userId;
    localStorage.setItem('teampit_room', roomId);
    localStorage.setItem('teampit_user', userId);
    
    document.getElementById('dash-room-id').textContent = roomId;
    document.getElementById('dash-user-id').textContent = userId;
    
    showPage('page-dashboard');
    refreshAll();
}

function goToEntry() {
    state.roomId = '';
    state.userId = '';
    showPage('page-entry');
    document.getElementById('entry-error').classList.add('d-none');
}

// ================================================================
// 入口：创建 / 加入
// ================================================================
document.getElementById('form-create').addEventListener('submit', async (e) => {
    e.preventDefault();
    const roomId = document.getElementById('create-room-id').value.trim();
    const ownerId = document.getElementById('create-owner-id').value.trim();
    const whitelistText = document.getElementById('create-whitelist').value;
    const userIds = whitelistText.split('\n').map(s => s.trim()).filter(Boolean);
    
    if (!roomId || !ownerId || userIds.length === 0) {
        showEntryError('请完整填写所有字段，白名单至少需要一人');
        return;
    }
    
    try {
        await apiCall('/api/rooms/create', 'POST', {
            room_id: roomId,
            owner_id: ownerId,
            user_ids: userIds,
        });
        goToDashboard(roomId, ownerId);
    } catch (err) {
        showEntryError(err.message);
    }
});

document.getElementById('form-join').addEventListener('submit', async (e) => {
    e.preventDefault();
    const roomId = document.getElementById('join-room-id').value.trim();
    const userId = document.getElementById('join-user-id').value.trim();
    
    if (!roomId || !userId) {
        showEntryError('请完整填写房间号和你的ID');
        return;
    }
    
    try {
        await apiCall('/api/rooms/join', 'POST', {
            room_id: roomId,
            user_id: userId,
        });
        goToDashboard(roomId, userId);
    } catch (err) {
        showEntryError(err.message);
    }
});

function showEntryError(msg) {
    const el = document.getElementById('entry-error');
    el.textContent = msg;
    el.classList.remove('d-none');
}

// ================================================================
// 退出
// ================================================================
document.getElementById('btn-leave').addEventListener('click', () => {
    if (confirm('确定要退出吗？')) {
        localStorage.removeItem('teampit_room');
        localStorage.removeItem('teampit_user');
        goToEntry();
    }
});

// ================================================================
// 自动登录检查
// ================================================================
function checkAutoLogin() {
    const roomId = localStorage.getItem('teampit_room');
    const userId = localStorage.getItem('teampit_user');
    if (roomId && userId) {
        apiCall('/api/rooms/join', 'POST', { room_id: roomId, user_id: userId })
            .then(() => goToDashboard(roomId, userId))
            .catch(() => {
                localStorage.removeItem('teampit_room');
                localStorage.removeItem('teampit_user');
            });
    }
}

// ================================================================
// 任务板
// ================================================================
async function refreshTasks() {
    try {
        const data = await apiCall(`/api/tasks?room_id=${state.roomId}&user_id=${state.userId}`);
        renderTasks(data.tasks);
    } catch (err) {
        console.error('刷新任务失败:', err);
    }
}

function renderTasks(tasks) {
    const lists = {
        todo: document.querySelector('.task-list[data-status="todo"]'),
        doing: document.querySelector('.task-list[data-status="doing"]'),
        done: document.querySelector('.task-list[data-status="done"]'),
    };
    
    for (const key in lists) {
        lists[key].innerHTML = '';
    }
    
    if (!tasks || tasks.length === 0) {
        for (const key in lists) {
            lists[key].innerHTML = '<div class="empty-hint">暂无任务</div>';
        }
        return;
    }
    
    for (const task of tasks) {
        const status = task.status || 'todo';
        const list = lists[status];
        if (!list) continue;
        
        const div = document.createElement('div');
        div.className = `task-item ${status}`;
        div.dataset.id = task.id;
        div.innerHTML = `
            <span class="task-title">${escapeHtml(task.title)}</span>
            <span class="task-assignee">${escapeHtml(task.assignee || '未指派')}</span>
            <div class="task-actions">
                <button class="btn-status" data-status="todo" title="待办">📋</button>
                <button class="btn-status" data-status="doing" title="进行中">⚡</button>
                <button class="btn-status" data-status="done" title="已完成">✅</button>
                <button class="btn-delete-task" title="删除">🗑️</button>
            </div>
        `;
        
        div.querySelectorAll('.btn-status').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                updateTaskStatus(task.id, btn.dataset.status);
            });
        });
        
        div.querySelector('.btn-delete-task').addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm('确定删除这个任务吗？')) {
                deleteTask(task.id);
            }
        });
        
        list.appendChild(div);
    }
}

async function updateTaskStatus(taskId, status) {
    try {
        await apiCall(`/api/tasks/${taskId}`, 'PUT', {
            room_id: state.roomId,
            user_id: state.userId,
            status: status,
        });
        refreshTasks();
    } catch (err) {
        alert('更新状态失败: ' + err.message);
    }
}

async function deleteTask(taskId) {
    try {
        await apiCall(`/api/tasks/${taskId}?room_id=${state.roomId}&user_id=${state.userId}`, 'DELETE');
        refreshTasks();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

document.getElementById('form-task').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = document.getElementById('task-title').value.trim();
    const assignee = document.getElementById('task-assignee').value.trim();
    const editId = document.getElementById('task-edit-id').value;
    
    if (!title) return;
    
    try {
        if (editId) {
            await apiCall(`/api/tasks/${editId}`, 'PUT', {
                room_id: state.roomId,
                user_id: state.userId,
                title: title,
                assignee: assignee || '',
            });
        } else {
            await apiCall('/api/tasks', 'POST', {
                room_id: state.roomId,
                user_id: state.userId,
                title: title,
                assignee: assignee || '',
            });
        }
        document.getElementById('form-task').reset();
        document.getElementById('task-edit-id').value = '';
        bootstrap.Modal.getInstance(document.getElementById('modal-task')).hide();
        refreshTasks();
    } catch (err) {
        alert('保存任务失败: ' + err.message);
    }
});

// ================================================================
// 灵感墙
// ================================================================
async function refreshIdeas() {
    try {
        const data = await apiCall(`/api/ideas?room_id=${state.roomId}&user_id=${state.userId}`);
        renderIdeas(data.ideas);
    } catch (err) {
        console.error('刷新灵感失败:', err);
    }
}

function renderIdeas(ideas) {
    const container = document.getElementById('idea-list');
    container.innerHTML = '';
    if (!ideas || ideas.length === 0) {
        container.innerHTML = '<div class="empty-hint">还没有灵感，来扔一个吧 💡</div>';
        return;
    }
    for (const idea of ideas) {
        const div = document.createElement('div');
        div.className = 'idea-item';
        div.innerHTML = `
            <span class="idea-content">${escapeHtml(idea.content)}</span>
            <span class="idea-meta">${escapeHtml(idea.author)} · ${formatTime(idea.created_at)}</span>
            ${idea.author === state.userId ? `<button class="btn-del-idea" data-id="${idea.id}">✕</button>` : ''}
        `;
        const delBtn = div.querySelector('.btn-del-idea');
        if (delBtn) {
            delBtn.addEventListener('click', () => deleteIdea(idea.id));
        }
        container.appendChild(div);
    }
}

async function deleteIdea(ideaId) {
    try {
        await apiCall(`/api/ideas/${ideaId}?room_id=${state.roomId}&user_id=${state.userId}`, 'DELETE');
        refreshIdeas();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

document.getElementById('form-idea').addEventListener('submit', async (e) => {
    e.preventDefault();
    const content = document.getElementById('idea-content').value.trim();
    if (!content) return;
    try {
        await apiCall('/api/ideas', 'POST', {
            room_id: state.roomId,
            user_id: state.userId,
            author: state.userId,
            content: content,
        });
        document.getElementById('idea-content').value = '';
        refreshIdeas();
    } catch (err) {
        alert('发布灵感失败: ' + err.message);
    }
});

// ================================================================
// 文件仓
// ================================================================
async function refreshFiles() {
    try {
        const data = await apiCall(`/api/files?room_id=${state.roomId}&user_id=${state.userId}`);
        renderFiles(data.files);
    } catch (err) {
        console.error('刷新文件失败:', err);
    }
}

function renderFiles(files) {
    const container = document.getElementById('file-list');
    container.innerHTML = '';
    if (!files || files.length === 0) {
        container.innerHTML = '<div class="col-12"><div class="empty-hint">还没有文件，上传一个吧 📁</div></div>';
        return;
    }
    for (const file of files) {
        const col = document.createElement('div');
        col.className = 'col-6 col-md-4 col-lg-3';
        const isImage = file.filename.match(/\.(png|jpg|jpeg|gif|bmp|webp|svg)$/i);
        col.innerHTML = `
            <div class="file-card">
                <div class="file-icon text-center">
                    ${isImage ? `<img src="/api/files/download/${file.id}?room_id=${state.roomId}&user_id=${state.userId}" class="file-preview-img" />` : `<i class="fas fa-file"></i>`}
                </div>
                <div class="file-name text-center">${escapeHtml(file.filename)}</div>
                <div class="text-center mt-1">
                    <span class="file-tag">${escapeHtml(file.tags || '未分类')}</span>
                </div>
                <div class="d-flex justify-content-between align-items-center mt-2">
                    <span class="file-uploader">${escapeHtml(file.uploaded_by)}</span>
                    <div>
                        <a href="/api/files/download/${file.id}?room_id=${state.roomId}&user_id=${state.userId}" class="btn btn-sm btn-outline-primary" target="_blank">⬇</a>
                        ${file.uploaded_by === state.userId ? `<button class="btn-del-file" data-id="${file.id}">🗑️</button>` : ''}
                    </div>
                </div>
            </div>
        `;
        const delBtn = col.querySelector('.btn-del-file');
        if (delBtn) {
            delBtn.addEventListener('click', () => deleteFile(file.id));
        }
        container.appendChild(col);
    }
}

async function deleteFile(fileId) {
    try {
        await apiCall(`/api/files/${fileId}?room_id=${state.roomId}&user_id=${state.userId}`, 'DELETE');
        refreshFiles();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

document.getElementById('form-file').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('file-input');
    const tags = document.getElementById('file-tags').value.trim();
    if (!input.files || input.files.length === 0) return;
    
    const file = input.files[0];
    const form = new FormData();
    form.append('room_id', state.roomId);
    form.append('user_id', state.userId);
    form.append('tags', tags);
    form.append('file', file);
    
    try {
        const resp = await fetch(`${API_BASE}/api/files/upload`, {
            method: 'POST',
            body: form,
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '上传失败');
        }
        input.value = '';
        document.getElementById('file-tags').value = '';
        refreshFiles();
    } catch (err) {
        alert('上传失败: ' + err.message);
    }
});

// ================================================================
// 每日站会（所有字段选填）
// ================================================================
async function refreshCheckins() {
    try {
        const data = await apiCall(`/api/checkins?room_id=${state.roomId}&user_id=${state.userId}`);
        renderCheckins(data.checkins);
        
        const todayData = await apiCall(`/api/checkins/today?room_id=${state.roomId}&user_id=${state.userId}`);
        const statusEl = document.getElementById('checkin-status');
        if (todayData.checkin) {
            statusEl.textContent = '✅ 今日已签到';
            statusEl.style.color = 'green';
        } else {
            statusEl.textContent = '⏳ 今日未签到';
            statusEl.style.color = '#dc3545';
        }
    } catch (err) {
        console.error('刷新站会失败:', err);
    }
}

function renderCheckins(checkins) {
    const container = document.getElementById('checkin-list');
    container.innerHTML = '';
    if (!checkins || checkins.length === 0) {
        container.innerHTML = '<div class="col-12"><div class="empty-hint">还没有签到记录</div></div>';
        return;
    }
    for (const c of checkins) {
        const div = document.createElement('div');
        div.className = 'col-12 col-md-6 col-lg-4';
        div.innerHTML = `
            <div class="checkin-card">
                <div class="d-flex justify-content-between">
                    <span class="checkin-user">${escapeHtml(c.user_id)}</span>
                    <span class="checkin-date">${escapeHtml(c.checkin_date)}</span>
                </div>
                <div class="mt-2">
                    <div><span class="checkin-label">昨天</span> ${escapeHtml(c.yesterday || '—')}</div>
                    <div><span class="checkin-label">今天</span> ${escapeHtml(c.today || '—')}</div>
                    <div><span class="checkin-label">阻碍</span> ${escapeHtml(c.blocked || '无')}</div>
                </div>
            </div>
        `;
        container.appendChild(div);
    }
}

// 站会提交：所有字段选填，全空也能提交
document.getElementById('form-checkin').addEventListener('submit', async (e) => {
    e.preventDefault();
    const yesterday = document.getElementById('checkin-yesterday').value.trim();
    const today = document.getElementById('checkin-today').value.trim();
    const blocked = document.getElementById('checkin-blocked').value.trim();
    
    try {
        await apiCall('/api/checkins', 'POST', {
            room_id: state.roomId,
            user_id: state.userId,
            yesterday: yesterday || '',
            today: today || '',
            blocked: blocked || '',
        });
        document.getElementById('checkin-yesterday').value = '';
        document.getElementById('checkin-today').value = '';
        document.getElementById('checkin-blocked').value = '';
        refreshCheckins();
    } catch (err) {
        alert('签到失败: ' + err.message);
    }
});

// ================================================================
// 工具函数
// ================================================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(dt) {
    if (!dt) return '';
    const d = new Date(dt);
    return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ================================================================
// 刷新全部
// ================================================================
function refreshAll() {
    refreshTasks();
    refreshIdeas();
    refreshFiles();
    refreshCheckins();
}

// ================================================================
// 初始化
// ================================================================
checkAutoLogin();
if (!state.roomId) {
    showPage('page-entry');
}

setInterval(() => {
    if (!document.getElementById('page-dashboard').classList.contains('d-none')) {
        refreshAll();
    }
}, 30000);

console.log('🏆 TeamPit 已加载');
