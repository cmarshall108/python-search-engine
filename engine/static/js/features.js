document.addEventListener('DOMContentLoaded', function() {
    // Theme Switcher
    const themeSwitcher = document.querySelector('.theme-switcher');
    if (themeSwitcher) {
        const themeOptions = themeSwitcher.querySelectorAll('.theme-option');
        
        themeOptions.forEach(option => {
            option.addEventListener('click', function() {
                const theme = this.getAttribute('data-theme');
                document.documentElement.setAttribute('data-theme', theme);
                
                // Update active class
                themeOptions.forEach(opt => opt.classList.remove('active'));
                this.classList.add('active');
                
                // Save preference
                localStorage.setItem('preferred-theme', theme);
            });
        });
        
        // Load saved theme
        const savedTheme = localStorage.getItem('preferred-theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
            themeOptions.forEach(opt => {
                if (opt.getAttribute('data-theme') === savedTheme) {
                    opt.classList.add('active');
                }
            });
        }
    }
    
    // View Switcher
    const viewSwitcher = document.querySelector('.view-switcher');
    if (viewSwitcher) {
        const viewOptions = viewSwitcher.querySelectorAll('.view-option');
        const resultsList = document.querySelector('.search-results');
        const visualResults = document.querySelector('.visual-results');
        
        viewOptions.forEach(option => {
            option.addEventListener('click', function() {
                const view = this.getAttribute('data-view');
                
                // Update active class
                viewOptions.forEach(opt => opt.classList.remove('active'));
                this.classList.add('active');
                
                // Toggle views
                if (view === 'list') {
                    resultsList.style.display = 'block';
                    visualResults.style.display = 'none';
                } else {
                    resultsList.style.display = 'none';
                    visualResults.style.display = 'grid';
                }
                
                // Save preference
                localStorage.setItem('preferred-view', view);
            });
        });
        
        // Load saved view
        const savedView = localStorage.getItem('preferred-view');
        if (savedView) {
            viewOptions.forEach(opt => {
                if (opt.getAttribute('data-view') === savedView) {
                    opt.click();
                }
            });
        }
    }
    
    // Time Machine Search
    const timeSlider = document.querySelector('.time-slider');
    if (timeSlider) {
        const timeHandle = timeSlider.querySelector('.time-handle');
        const timeDisplay = document.querySelector('.time-display');
        const currentYear = new Date().getFullYear();
        let isDragging = false;
        
        function updateTimePosition(e) {
            const rect = timeSlider.getBoundingClientRect();
            const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
            const percentage = x / rect.width;
            
            // Calculate year between 2000 and current year
            const year = 2000 + Math.round(percentage * (currentYear - 2000));
            
            timeHandle.style.left = `${percentage * 100}%`;
            timeDisplay.textContent = year;
            
            // Here you would trigger a search with the historical context
            // debounce this for performance
        }
        
        timeSlider.addEventListener('mousedown', function(e) {
            isDragging = true;
            updateTimePosition(e);
        });
        
        document.addEventListener('mousemove', function(e) {
            if (isDragging) {
                updateTimePosition(e);
            }
        });
        
        document.addEventListener('mouseup', function() {
            isDragging = false;
        });
    }
    
    // Focus Mode Toggle
    const focusModeToggle = document.querySelector('.focus-mode-toggle');
    if (focusModeToggle) {
        focusModeToggle.addEventListener('click', function() {
            document.body.classList.toggle('focus-mode');
            this.classList.toggle('focus-mode-active');
            
            // Save preference
            const isFocusMode = document.body.classList.contains('focus-mode');
            localStorage.setItem('focus-mode', isFocusMode ? 'enabled' : 'disabled');
        });
        
        // Load saved preference
        const savedFocusMode = localStorage.getItem('focus-mode');
        if (savedFocusMode === 'enabled') {
            document.body.classList.add('focus-mode');
            focusModeToggle.classList.add('focus-mode-active');
        }
    }
    
    // Generate AI summary for the search query
    function generateAISummary(query) {
        const summaryBox = document.querySelector('.ai-summary-content');
        if (summaryBox && query) {
            // In a real implementation, this would call an API
            // This is a simplified example
            const summaries = {
                'javascript': 'JavaScript is a programming language that enables interactive web pages. It\'s commonly used for client-side web development, but also for server-side with Node.js. Key features include first-class functions, dynamic typing, and prototype-based object-orientation.',
                'python': 'Python is a high-level, interpreted programming language known for its readability and versatility. It\'s widely used in data science, machine learning, web development, and automation.',
                'climate change': 'Climate change refers to long-term shifts in temperatures and weather patterns. Human activities have been the main driver since the 1800s, primarily due to burning fossil fuels like coal, oil and gas which produces heat-trapping gases.',
                'artificial intelligence': 'Artificial Intelligence (AI) is the simulation of human intelligence in machines. Machine learning, neural networks, and deep learning are subsets of AI that enable computers to learn from data and improve over time without explicit programming.'
            };
            
            // Check if we have a pre-defined summary or generate a generic one
            let summary = summaries[query.toLowerCase()];
            if (!summary) {
                summary = `Search results for "${query}" include various websites that may provide information, products, or services related to your query. Explore the results below to find what you're looking for.`;
            }
            
            summaryBox.textContent = summary;
        }
    }
    
    // Get the current query and generate summary
    const queryInput = document.getElementById('search-input');
    if (queryInput && queryInput.value) {
        generateAISummary(queryInput.value);
    }
});
