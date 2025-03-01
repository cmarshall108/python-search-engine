document.addEventListener('DOMContentLoaded', function() {
    // WebSocket connection
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    let reconnectInterval = null;
    let lastMessageTime = 0;
    
    // Debug output
    const debugArea = document.createElement('div');
    debugArea.className = 'debug-area';
    debugArea.innerHTML = '<h4>Debug Log</h4><pre id="debug-log" style="height:200px;overflow:auto;background:#f5f5f5;padding:10px;font-size:12px;"></pre>';
    document.querySelector('.admin-content').appendChild(debugArea);
    const debugLog = document.getElementById('debug-log');
    
    function logDebug(message, data) {
        const timestamp = new Date().toLocaleTimeString();
        let logMessage = `[${timestamp}] ${message}`;
        if (data) {
            if (typeof data === 'object') {
                logMessage += `: ${JSON.stringify(data)}`;
            } else {
                logMessage += `: ${data}`;
            }
        }
        debugLog.innerHTML += logMessage + '\n';
        debugLog.scrollTop = debugLog.scrollHeight;
        console.log(logMessage);
    }
    
    // DOM elements
    const crawlerForm = document.getElementById('crawler-form');
    const crawlerUrlInput = document.getElementById('crawler-url');
    const crawlerDepthSelect = document.getElementById('crawler-depth');
    const startCrawlerBtn = document.getElementById('start-crawler');
    const statusPanel = document.getElementById('crawler-status-panel');
    const statusText = document.getElementById('crawler-status-text');
    const progressBar = document.getElementById('crawler-progress-bar');
    const currentUrl = document.getElementById('current-url');
    const recentUrlsList = document.getElementById('recent-urls');
    const saveIndexBtn = document.getElementById('save-index');
    const loadIndexBtn = document.getElementById('load-index');
    
    // Stats elements
    const statCrawled = document.getElementById('stat-crawled');
    const statIndexed = document.getElementById('stat-indexed');
    const statQueued = document.getElementById('stat-queued');
    const statErrors = document.getElementById('stat-errors');
    const statTime = document.getElementById('stat-time');
    
    // Debug - Add status indicator to page
    const debugStatus = document.createElement('div');
    debugStatus.className = 'websocket-status';
    debugStatus.innerHTML = 'WebSocket: <span id="ws-status">Connecting...</span>';
    document.querySelector('.admin-header').appendChild(debugStatus);
    const wsStatusIndicator = document.getElementById('ws-status');
    
    // Add a test button for WebSocket
    const testBtn = document.createElement('button');
    testBtn.className = 'admin-button';
    testBtn.innerHTML = '<i class="fas fa-vial"></i> Test WebSocket';
    testBtn.style.marginLeft = '10px';
    testBtn.addEventListener('click', function() {
        // First try to send a test message through the WebSocket
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'test', timestamp: Date.now() }));
            logDebug('Sent test request through WebSocket');
        }
        
        // Also try the API endpoint
        fetch('/api/crawler/test', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            logDebug('Test response from API', data);
        })
        .catch(error => {
            logDebug('Error testing WebSocket', error);
        });
    });
    document.querySelector('.websocket-status').appendChild(testBtn);
    
    // Initialize the WebSocket connection
    function connectWebSocket() {
        // Close existing connection if any
        if (ws) {
            try {
                ws.close();
            } catch (e) {
                logDebug('Error closing existing WebSocket', e);
            }
        }
        
        // Clear any existing reconnect interval
        if (reconnectInterval) {
            clearTimeout(reconnectInterval);
            reconnectInterval = null;
        }
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/crawler`;
        
        logDebug(`Connecting to WebSocket at ${wsUrl}`);
        wsStatusIndicator.textContent = 'Connecting...';
        wsStatusIndicator.style.color = 'orange';
        
        try {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {
                logDebug('WebSocket connection established');
                wsStatusIndicator.textContent = 'Connected';
                wsStatusIndicator.style.color = 'green';
                reconnectAttempts = 0; // Reset reconnect counter on successful connection
                lastMessageTime = Date.now();
                
                // Send an immediate ping to verify communication
                ws.send(JSON.stringify({ 
                    type: 'ping',
                    timestamp: Date.now(),
                    client: 'admin-ui'
                }));
            };
            
            ws.onmessage = function(event) {
                lastMessageTime = Date.now();
                let data;
                
                try {
                    data = JSON.parse(event.data);
                    // Only log non-ping/pong messages to avoid log spam
                    if (data.status !== 'ping' && data.type !== 'pong') {
                        logDebug('WebSocket message received', data);
                    }
                    handleCrawlerUpdate(data);
                    
                    // Flash the status indicator to show activity
                    wsStatusIndicator.className = 'websocket-active';
                    setTimeout(() => { wsStatusIndicator.className = ''; }, 500);
                } catch (e) {
                    logDebug('Error parsing WebSocket message', e);
                    logDebug('Raw message', event.data);
                }
            };
            
            ws.onclose = function(event) {
                logDebug('WebSocket connection closed', {
                    code: event.code,
                    reason: event.reason,
                    wasClean: event.wasClean
                });
                wsStatusIndicator.textContent = 'Disconnected';
                wsStatusIndicator.style.color = 'red';
                
                // Don't attempt to reconnect if the page is being unloaded
                if (isPageUnloading) {
                    return;
                }
                
                // Attempt to reconnect if we haven't exceeded the limit and the close was not intentional
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    // Exponential backoff: increase timeout for each failed attempt
                    const timeout = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 10000);
                    logDebug(`Attempting to reconnect in ${timeout}ms (attempt ${reconnectAttempts})`);
                    
                    // Use setTimeout for reconnect attempt
                    reconnectInterval = setTimeout(connectWebSocket, timeout);
                } else {
                    wsStatusIndicator.textContent = 'Failed to Connect';
                    logDebug('Max reconnection attempts reached');
                }
            };
            
            ws.onerror = function(error) {
                logDebug('WebSocket error', error);
                wsStatusIndicator.textContent = 'Error';
                wsStatusIndicator.style.color = 'red';
            };
        } catch (e) {
            logDebug('Error creating WebSocket', e);
            wsStatusIndicator.textContent = 'Error';
            wsStatusIndicator.style.color = 'red';
        }
    }
    
    // Handle crawler status updates
    function handleCrawlerUpdate(data) {
        // Add timestamp for debug purposes
        const timestamp = new Date().toLocaleTimeString();
        logDebug(`Update at ${timestamp}:`, data);
        
        // Reset the update timer
        lastUpdateTime = Date.now();
        updateLastUpdateTimer();
        
        // Flash the status indicator to show activity
        wsStatusIndicator.className = 'websocket-active';
        setTimeout(() => { wsStatusIndicator.className = ''; }, 500);
        
        // Switch based on the status field in the message
        switch (data.status) {
            case 'welcome':
                logDebug('WebSocket welcome message received');
                addActivityItem('info', 'WebSocket connection established');
                break;
                
            case 'ping':
            case 'pong':
                logDebug(`WebSocket ${data.status} received`);
                break;
                
            case 'test':
                logDebug('Test message received');
                addActivityItem('info', 'Test message received');
                break;
                
            case 'connected':
                // Initial connection, update with current stats
                logDebug('Initial stats received');
                if (data.stats) {
                    updateCrawlerStats(data.stats);
                    updateUIBasedOnStatus(data.stats.status);
                    addActivityItem('info', `Reconnected to crawler (status: ${data.stats.status})`);
                }
                break;
                
            case 'started':
                statusText.textContent = 'Starting...';
                updateStatusDot('running');
                animateStatusDots();
                statusPanel.style.display = 'block';
                startCrawlerBtn.disabled = true;
                progressBar.style.width = '0%';
                progressPercentage.textContent = '0%';
                progressRatio.textContent = '(0/0)';
                recentUrlsList.innerHTML = '';
                addActivityItem('info', `Started crawling: ${data.url} (depth ${data.depth})`);
                break;
                
            case 'crawling':
                statusText.textContent = 'Crawling...';
                updateStatusDot('running');
                currentUrl.textContent = data.url || 'Unknown';
                addActivityItem('info', `Crawling: ${data.url}`);
                break;
                
            case 'progress':
                updateCrawlerStats(data.stats);
                // Update progress bar based on queue ratio
                if (data.stats) {
                    const crawled = data.stats.crawled || 0;
                    const queued = data.stats.queued || 0;
                    const total = crawled + queued;
                    const progress = total > 0 ? (crawled / total) * 100 : 0;
                    
                    progressBar.style.width = `${Math.min(progress, 100)}%`;
                    progressPercentage.textContent = `${Math.round(progress)}%`;
                    progressRatio.textContent = `(${crawled}/${total})`;
                    statTime.textContent = `${data.elapsed || 0}s`;
                }
                break;
                
            case 'completed':
                statusText.textContent = 'Completed';
                updateStatusDot('completed');
                stopAnimatingStatusDots();
                progressBar.style.width = '100%';
                progressPercentage.textContent = '100%';
                startCrawlerBtn.disabled = false;
                updateCrawlerStats(data.stats);
                if (data.elapsed) {
                    statTime.textContent = `${data.elapsed}s`;
                }
                addActivityItem('success', `Crawling completed! Processed ${data.stats?.crawled || 0} pages in ${data.elapsed || 0} seconds`);
                break;
                
            case 'error':
                statusText.textContent = 'Error';
                updateStatusDot('error');
                stopAnimatingStatusDots();
                startCrawlerBtn.disabled = false;
                addActivityItem('error', `Error: ${data.message || 'Unknown error'}`);
                alert(`Crawler error: ${data.message || 'Unknown error'}`);
                break;
                
            default:
                logDebug('Unknown status update', data);
        }
    }
    
    // Update UI elements based on crawler status
    function updateUIBasedOnStatus(status) {
        if (status === 'running') {
            statusPanel.style.display = 'block';
            startCrawlerBtn.disabled = true;
            statusText.textContent = 'Crawling...';
        } else if (status === 'completed') {
            statusPanel.style.display = 'block';
            startCrawlerBtn.disabled = false;
            statusText.textContent = 'Completed';
            progressBar.style.width = '100%';
        } else if (status === 'error') {
            statusPanel.style.display = 'block';
            startCrawlerBtn.disabled = false;
            statusText.textContent = 'Error';
        } else {
            statusPanel.style.display = 'none';
            startCrawlerBtn.disabled = false;
        }
    }
    
    // Update the status dot visual indicator
    function updateStatusDot(status) {
        const statusDot = document.getElementById('status-dot');
        if (!statusDot) return;
        
        // Remove all status classes
        statusDot.classList.remove('idle', 'running', 'completed', 'error');
        
        // Add the appropriate class
        statusDot.classList.add(status);
    }
    
    // Animate the status dots for running state
    let statusDotsInterval = null;
    function animateStatusDots() {
        if (statusDotsInterval) {
            clearInterval(statusDotsInterval);
        }
        
        const animationEl = document.getElementById('status-animation');
        if (!animationEl) return;
        
        let dots = 0;
        statusDotsInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            animationEl.textContent = '.'.repeat(dots);
        }, 500);
    }
    
    function stopAnimatingStatusDots() {
        if (statusDotsInterval) {
            clearInterval(statusDotsInterval);
            statusDotsInterval = null;
        }
        
        const animationEl = document.getElementById('status-animation');
        if (animationEl) animationEl.textContent = '';
    }
    
    // Add an activity item to the feed
    function addActivityItem(type, message) {
        const activityFeed = document.getElementById('activity-feed');
        if (!activityFeed) return;
        
        const now = new Date();
        const timestamp = now.toLocaleTimeString();
        
        const item = document.createElement('div');
        item.className = 'activity-item';
        
        item.innerHTML = `
            <span class="activity-timestamp">[${timestamp}]</span>
            <span class="activity-type ${type}">${type.toUpperCase()}</span>
            <span class="activity-message">${message}</span>
        `;
        
        activityFeed.appendChild(item);
        
        // Scroll to bottom
        activityFeed.scrollTop = activityFeed.scrollHeight;
        
        // Limit the number of items (keep last 50)
        while (activityFeed.children.length > 50) {
            activityFeed.removeChild(activityFeed.children[0]);
        }
    }
    
    // Track last update time and show countdown
    let lastUpdateTime = Date.now();
    let updateTimerInterval = null;
    
    function updateLastUpdateTimer() {
        const timerEl = document.getElementById('last-update-time');
        if (!timerEl) return;
        
        if (updateTimerInterval) {
            clearInterval(updateTimerInterval);
        }
        
        updateTimerInterval = setInterval(() => {
            const now = Date.now();
            const elapsedSeconds = Math.round((now - lastUpdateTime) / 1000);
            timerEl.textContent = `${elapsedSeconds}s`;
        }, 1000);
    }
    
    // Update crawler statistics and recently crawled URLs
    function updateCrawlerStats(stats) {
        if (!stats) return;
        
        logDebug('Updating stats with:', stats);
        
        // Update stat counters
        statCrawled.textContent = stats.crawled || 0;
        statIndexed.textContent = stats.indexed || 0;
        statQueued.textContent = stats.queued || 0;
        statErrors.textContent = stats.errors || 0;
        
        // If index stats are available
        if (stats.index_stats) {
            document.getElementById('stat-documents').textContent = stats.index_stats.documents || 0;
            document.getElementById('stat-keywords').textContent = stats.index_stats.keywords || 0;
            document.getElementById('stat-index-size').textContent = stats.index_stats.size || '0 KB';
        }
        
        if (stats.current_url) {
            currentUrl.textContent = stats.current_url;
        }
        
        // Update the recently crawled URLs
        if (stats.recent_urls && stats.recent_urls.length) {
            // Keep existing items
            const existingUrls = new Set();
            Array.from(recentUrlsList.children).forEach(item => {
                const link = item.querySelector('a');
                if (link) existingUrls.add(link.href);
            });
            
            // Add new items at the beginning
            stats.recent_urls.forEach(item => {
                if (!existingUrls.has(item.url)) {
                    const li = document.createElement('li');
                    li.className = 'recent-url-item';
                    
                    const a = document.createElement('a');
                    a.href = item.url;
                    a.target = '_blank';
                    a.textContent = item.title || item.url;
                    
                    li.appendChild(a);
                    
                    // Insert at the beginning
                    if (recentUrlsList.firstChild) {
                        recentUrlsList.insertBefore(li, recentUrlsList.firstChild);
                    } else {
                        recentUrlsList.appendChild(li);
                    }
                    
                    // Highlight briefly
                    setTimeout(() => {
                        li.style.backgroundColor = 'rgba(66, 133, 244, 0.1)';
                        setTimeout(() => {
                            li.style.backgroundColor = '';
                        }, 2000);
                    }, 0);
                    
                    existingUrls.add(item.url);
                }
            });
            
            // Limit to 15 items
            while (recentUrlsList.children.length > 15) {
                recentUrlsList.removeChild(recentUrlsList.lastChild);
            }
        }
    }
    
    // Start the crawler
    crawlerForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const url = crawlerUrlInput.value;
        const depth = crawlerDepthSelect.value;
        const forceRecrawl = document.getElementById('force-recrawl')?.checked || false;
        
        if (!url) {
            alert('Please enter a URL to crawl');
            return;
        }
        
        console.log(`Starting crawler with URL: ${url}, depth: ${depth}, force: ${forceRecrawl}`);
        
        fetch('/api/crawl', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `url=${encodeURIComponent(url)}&depth=${depth}&force=${forceRecrawl}`
        })
        .then(response => response.json())
        .then(data => {
            console.log('Crawler start response:', data);
            if (data.status === 'error') {
                alert(`Error: ${data.message}`);
            } else {
                // Immediately update UI for better responsiveness
                statusPanel.style.display = 'block';
                startCrawlerBtn.disabled = true;
                statusText.textContent = 'Starting...';
                progressBar.style.width = '0%';
                
                // Add a message about force recrawl if enabled
                if (forceRecrawl) {
                    addActivityItem('info', 'Force recrawl enabled - will recrawl previously visited URLs');
                }
            }
        })
        .catch(error => {
            console.error('Error starting crawler:', error);
            alert('Error starting crawler. Please try again.');
        });
    });
    
    // Add a ping function to keep the WebSocket alive
    function pingWebSocket() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify({ 
                    type: 'ping',
                    timestamp: Date.now()
                }));
                // Don't log every ping to avoid console spam
            } catch (e) {
                logDebug('Error sending ping', e);
            }
        }
    }
    
    // Ping the server every 25 seconds to keep the connection alive
    // This is slightly less than the server's 30-second ping interval
    const pingInterval = setInterval(pingWebSocket, 25000);
    
    // Save index
    saveIndexBtn.addEventListener('click', function() {
        fetch('/api/save_index', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
        })
        .catch(error => {
            console.error('Error saving index:', error);
            alert('Error saving index. Please try again.');
        });
    });
    
    // Load index
    loadIndexBtn.addEventListener('click', function() {
        fetch('/api/load_index', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
        })
        .catch(error => {
            console.error('Error loading index:', error);
            alert('Error loading index. Please try again.');
        });
    });
    
    // Add a manual reconnect button
    const reconnectBtn = document.createElement('button');
    reconnectBtn.className = 'admin-button';
    reconnectBtn.style.marginLeft = '10px';
    reconnectBtn.innerHTML = '<i class="fas fa-sync"></i> Reconnect';
    reconnectBtn.addEventListener('click', connectWebSocket);
    document.querySelector('.websocket-status').appendChild(reconnectBtn);
    
    // Initialize the page
    function init() {
        // Add initial activity entry
        addActivityItem('info', 'Admin dashboard initialized');
        
        // Check if the crawler is already running
        fetch('/api/crawler/status')
            .then(response => response.json())
            .then(data => {
                console.log('Initial crawler status:', data);
                if (data) {
                    updateUIBasedOnStatus(data.status);
                    updateCrawlerStats(data);
                    
                    // Check what status to display
                    if (data.status === 'running') {
                        statusPanel.style.display = 'block';
                        startCrawlerBtn.disabled = true;
                        updateStatusDot('running');
                        animateStatusDots();
                        addActivityItem('info', 'Connected to active crawler');
                    } else if (data.status === 'completed') {
                        statusPanel.style.display = 'block';
                        startCrawlerBtn.disabled = false;
                        updateStatusDot('completed');
                    } else if (data.status === 'error') {
                        statusPanel.style.display = 'block';
                        startCrawlerBtn.disabled = false;
                        updateStatusDot('error');
                    } else {
                        statusPanel.style.display = 'none';
                        updateStatusDot('idle');
                    }
                }
            })
            .catch(error => {
                console.error('Error checking crawler status:', error);
                addActivityItem('error', 'Failed to check crawler status');
            });
            
        // Connect to WebSocket
        connectWebSocket();
    }
    
    // Flag to detect if the page is being unloaded
    let isPageUnloading = false;
    
    // Clean up on page unload
    window.addEventListener('beforeunload', function() {
        isPageUnloading = true;
        if (ws) {
            ws.close(1000, "Page unloaded"); // Use 1000 (normal closure) code
        }
        if (reconnectInterval) {
            clearTimeout(reconnectInterval);
        }
        clearInterval(pingInterval);
        if (healthCheckInterval) {
            clearInterval(healthCheckInterval);
        }
        if (updateTimerInterval) {
            clearInterval(updateTimerInterval);
        }
    });
    
    // Add a health check to verify WebSocket is working
    const healthCheckInterval = setInterval(function() {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        // If we haven't received any message in 30 seconds, reconnect
        // This is a longer timeout to prevent frequent reconnects
        const now = Date.now();
        if (now - lastMessageTime > 30000) { 
            logDebug('No messages received in 30 seconds, reconnecting');
            if (ws) {
                ws.close(1001, "Health check timeout");  // Use 1001 (going away) code
            }
            reconnectAttempts = 0; // Reset attempts for a fresh start
            connectWebSocket();
        }
    }, 10000);
    
    // Start initialization
    init();
    
    // Initialize elements for progress display
    const progressPercentage = document.getElementById('progress-percentage');
    const progressRatio = document.getElementById('progress-ratio');
    
    // Initialize the last update timer
    updateLastUpdateTimer();
    
    // Add a "Clear Index" button handler
    const clearIndexBtn = document.getElementById('clear-index');
    if (clearIndexBtn) {
        clearIndexBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to clear the search index? This cannot be undone.')) {
                fetch('/api/clear_index', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    addActivityItem('info', 'Search index cleared');
                })
                .catch(error => {
                    console.error('Error clearing index:', error);
                    alert('Error clearing index. Please try again.');
                });
            }
        });
    }
    
    // Resume crawler
    const resumeCrawlerBtn = document.getElementById('resume-crawler');
    if (resumeCrawlerBtn) {
        resumeCrawlerBtn.addEventListener('click', function() {
            const depth = crawlerDepthSelect.value;
            
            fetch('/api/crawler/resume', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `depth=${depth}`
            })
            .then(response => response.json())
            .then(data => {
                console.log('Crawler resume response:', data);
                if (data.status === 'error') {
                    alert(`Error: ${data.message}`);
                } else {
                    // Update UI for resumed crawling
                    statusPanel.style.display = 'block';
                    startCrawlerBtn.disabled = true;
                    resumeCrawlerBtn.disabled = true;
                    statusText.textContent = 'Resuming...';
                    addActivityItem('info', 'Resuming previous crawl');
                }
            })
            .catch(error => {
                console.error('Error resuming crawler:', error);
                alert('Error resuming crawler. Please try again.');
            });
        });
    }
    
    // Stop crawler
    const stopCrawlerBtn = document.getElementById('stop-crawler');
    if (stopCrawlerBtn) {
        stopCrawlerBtn.addEventListener('click', function() {
            fetch('/api/crawler/stop', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                console.log('Crawler stop response:', data);
                if (data.status === 'error') {
                    alert(`Error: ${data.message}`);
                } else {
                    // Update UI for stopped crawling
                    statusText.textContent = 'Stopping...';
                    addActivityItem('info', 'Stopping crawler and saving state');
                }
            })
            .catch(error => {
                console.error('Error stopping crawler:', error);
                alert('Error stopping crawler. Please try again.');
            });
        });
    }
    
    // Clear cache buttons
    const clearCacheBtn = document.getElementById('clear-cache');
    if (clearCacheBtn) {
        clearCacheBtn.addEventListener('click', function() {
            fetch('/api/cache/clear', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                addActivityItem('info', data.message);
            })
            .catch(error => {
                console.error('Error clearing cache:', error);
                alert('Error clearing cache. Please try again.');
            });
        });
    }
    
    const clearAllCacheBtn = document.getElementById('clear-all-cache');
    if (clearAllCacheBtn) {
        clearAllCacheBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to clear all cached pages? This cannot be undone.')) {
                fetch('/api/cache/clear', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: 'all=true'
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    addActivityItem('info', data.message);
                })
                .catch(error => {
                    console.error('Error clearing all cache:', error);
                    alert('Error clearing all cache. Please try again.');
                });
            }
        });
    }
    
    // Update storage stats when available
    function updateStorageStats(stats) {
        if (!stats || !stats.storage_stats) return;
        
        const storageStats = stats.storage_stats;
        
        document.getElementById('original-size').textContent = storageStats.original_size;
        document.getElementById('compressed-size').textContent = storageStats.compressed_size;
        document.getElementById('storage-saved').textContent = `Saved: ${storageStats.savings}`;
        document.getElementById('storage-percent').textContent = `${storageStats.savings_percent}%`;
        
        // Update chart
        const chartFill = document.getElementById('storage-chart-fill');
        if (chartFill) {
            chartFill.style.width = `${100 - storageStats.savings_percent}%`;
        }
    }
    
    // Extend handleCrawlerUpdate to handle stopping status
    const originalHandleCrawlerUpdate = handleCrawlerUpdate;
    handleCrawlerUpdate = function(data) {
        // Call original function
        originalHandleCrawlerUpdate(data);
        
        // Add special handling for stopping status
        if (data.status === 'stopping') {
            statusText.textContent = 'Stopping...';
            updateStatusDot('running');
            startCrawlerBtn.disabled = true;
            if (resumeCrawlerBtn) resumeCrawlerBtn.disabled = true;
        }
        
        // Handle storage stats if available
        if (data.stats && data.stats.storage_stats) {
            updateStorageStats(data.stats);
        }
    };
});
