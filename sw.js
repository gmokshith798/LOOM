// Loom Persistent Background Service Worker
const FIREBASE_URL = 'https://loom-4e53.onrender.com/api';

let lastKnownTs = null;
let knownIds = {
  chatMessages: new Set(),
  assignments: new Set(),
  notes: new Set(),
  homeworks: new Set(),
  syllabuses: new Set()
};

const CURRENT_CACHE_NAME = 'loom-v20260909-03';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(keys.map(k => {
        if (k !== CURRENT_CACHE_NAME) {
          return caches.delete(k);
        }
      }));
    }).then(() => clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || event.request.url.includes('/api/')) {
    return;
  }
  // For navigation / HTML requests, always bypass cache to guarantee fresh version
  if (event.request.mode === 'navigate' || event.request.destination === 'document' || event.request.url.endsWith('index.html') || event.request.url.endsWith('/')) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' }).catch(() => caches.match(event.request))
    );
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'INIT_SNAPSHOT') {
    if (event.data.knownIds) {
      Object.keys(event.data.knownIds).forEach(k => {
        if (event.data.knownIds[k] && Array.isArray(event.data.knownIds[k])) {
          knownIds[k] = new Set(event.data.knownIds[k]);
        }
      });
    }
  }
});

let lastEtag = null;

async function checkCloudUpdatesInBackground() {
  try {
    const headers = {};
    if (lastEtag) headers['If-None-Match'] = lastEtag;

    const res = await fetch(FIREBASE_URL + '/store.json', { headers });
    if (res.status === 304) return; // 0 bytes downloaded if unchanged!
    if (!res.ok) return;

    const etag = res.headers.get('ETag');
    if (etag) lastEtag = etag;

    const cloud = await res.json();
    if (!cloud) return;

    if (!lastKnownTs) {
      ['assignments', 'notes', 'homeworks', 'syllabuses', 'chatMessages'].forEach(k => {
        if (cloud[k]) {
          const list = Array.isArray(cloud[k]) ? cloud[k] : Object.values(cloud[k]);
          list.forEach(item => { if (item && item.id) knownIds[k].add(item.id); });
        }
      });
      lastKnownTs = Date.now();
      return;
    }

    lastKnownTs = Date.now();

    // Check New Assignments
    if (cloud.assignments) {
      const list = Array.isArray(cloud.assignments) ? cloud.assignments : Object.values(cloud.assignments);
      list.forEach(a => {
        if (a && a.id && !knownIds.assignments.has(a.id)) {
          knownIds.assignments.add(a.id);
          self.registration.showNotification('📝 Loom: New Assignment / DPP', {
            body: `${a.title || 'New Assignment'} (${a.subject || 'JEE'})`,
            tag: a.id,
            vibrate: [200, 100, 200],
            data: { url: '/' }
          });
        }
      });
    }

    // Check New Class Notes
    if (cloud.notes) {
      const list = Array.isArray(cloud.notes) ? cloud.notes : Object.values(cloud.notes);
      list.forEach(n => {
        if (n && n.id && !knownIds.notes.has(n.id)) {
          knownIds.notes.add(n.id);
          self.registration.showNotification('📚 Loom: New Daily Class Notes', {
            body: `${n.title || 'New Notes'} - Topic: ${n.topic || 'Class Material'}`,
            tag: n.id,
            vibrate: [200, 100, 200],
            data: { url: '/' }
          });
        }
      });
    }

    // Check New Homework
    if (cloud.homeworks) {
      const list = Array.isArray(cloud.homeworks) ? cloud.homeworks : Object.values(cloud.homeworks);
      list.forEach(h => {
        if (h && h.id && !knownIds.homeworks.has(h.id)) {
          knownIds.homeworks.add(h.id);
          self.registration.showNotification('🏠 Loom: New Daily Homework', {
            body: `${h.title || 'New Homework'} (${h.subject || 'JEE'})`,
            tag: h.id,
            vibrate: [200, 100, 200],
            data: { url: '/' }
          });
        }
      });
    }

    // Check New Syllabus
    if (cloud.syllabuses) {
      const list = Array.isArray(cloud.syllabuses) ? cloud.syllabuses : Object.values(cloud.syllabuses);
      list.forEach(s => {
        if (s && s.id && !knownIds.syllabuses.has(s.id)) {
          knownIds.syllabuses.add(s.id);
          self.registration.showNotification('📅 Loom: New Exam Syllabus Schedule', {
            body: `${s.examTitle || 'New Syllabus'} (${s.examType || 'Exam'})`,
            tag: s.id,
            vibrate: [200, 100, 200],
            data: { url: '/' }
          });
        }
      });
    }

    // Check New Chat Messages
    if (cloud.chatMessages) {
      const list = Array.isArray(cloud.chatMessages) ? cloud.chatMessages : Object.values(cloud.chatMessages);
      list.forEach(cm => {
        if (cm && cm.id && !knownIds.chatMessages.has(cm.id)) {
          knownIds.chatMessages.add(cm.id);
          self.registration.showNotification('💬 Loom: New Chat Message', {
            body: `${cm.senderName || 'User'}: "${cm.text ? cm.text.substring(0, 50) : 'Sent an attachment'}"`,
            tag: cm.id,
            vibrate: [200, 100, 200],
            data: { url: '/' }
          });
        }
      });
    }
  } catch(e) {}
}

setInterval(() => {
  checkCloudUpdatesInBackground();
}, 30000);

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (let i = 0; i < clientList.length; i++) {
        let client = clientList[i];
        if (client.url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(event.notification.data ? event.notification.data.url : '/');
      }
    })
  );
});
