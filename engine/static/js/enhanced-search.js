document.addEventListener('DOMContentLoaded', function() {
  // Initialize theme
  initTheme();

  // Initialize search type tabs
  initSearchTabs();

  // Initialize lightbox for image results
  initLightbox();

  // Initialize search suggestions
  initSearchSuggestions();

  // Initialize voice search
  initVoiceSearch();

  // Initialize infinite scroll for image results
  if (document.querySelector('.image-results')) {
    initInfiniteScroll();
  }
});

// Theme switcher
function initTheme() {
  const themeButton = document.querySelector('.theme-button');
  if (!themeButton) return;

  // Check for saved theme preference or respect OS preference
  const savedTheme = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    document.documentElement.setAttribute('data-theme', 'dark');
    updateThemeButton(true);
  }

  // Theme button click handler
  themeButton.addEventListener('click', function() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
    updateThemeButton(!isDark);
  });

  function updateThemeButton(isDark) {
    const icon = themeButton.querySelector('i');
    if (isDark) {
      icon.classList.remove('fa-moon');
      icon.classList.add('fa-sun');
    } else {
      icon.classList.remove('fa-sun');
      icon.classList.add('fa-moon');
    }
  }
}

// Search type tabs functionality
function initSearchTabs() {
  const searchFilters = document.querySelectorAll('.search-filter');
  if (!searchFilters.length) return;

  searchFilters.forEach(filter => {
    filter.addEventListener('click', function() {
      // Remove active class from all filters
      searchFilters.forEach(f => f.classList.remove('active'));
      
      // Add active class to clicked filter
      this.classList.add('active');
      
      // Update hidden input if it exists
      const searchTypeInput = document.getElementById('search-type');
      if (searchTypeInput) {
        searchTypeInput.value = this.dataset.type;
      }
      
      // If we're on results page, submit form to update results
      if (window.location.pathname.includes('/search')) {
        document.getElementById('search-form').submit();
      }
    });
  });
}

// Lightbox for image results
function initLightbox() {
  const lightbox = document.getElementById('lightbox');
  if (!lightbox) return;
  
  const lightboxImg = document.getElementById('lightbox-image');
  const lightboxClose = document.querySelector('.lightbox-close');
  
  // Open lightbox when clicking on image result
  document.querySelectorAll('.image-result').forEach(result => {
    result.addEventListener('click', function() {
      const imgSrc = this.querySelector('img').src.replace('thumbnail', 'large');
      const imgAlt = this.querySelector('img').alt;
      
      lightboxImg.src = imgSrc;
      lightboxImg.alt = imgAlt;
      lightbox.classList.add('active');
      
      // Prevent page scrolling when lightbox is open
      document.body.style.overflow = 'hidden';
    });
  });
  
  // Close lightbox 
  if (lightboxClose) {
    lightboxClose.addEventListener('click', closeLightbox);
  }
  
  // Also close lightbox when clicking outside the image
  lightbox.addEventListener('click', function(event) {
    if (event.target === lightbox) {
      closeLightbox();
    }
  });
  
  // Close with escape key
  document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape' && lightbox.classList.contains('active')) {
      closeLightbox();
    }
  });
  
  function closeLightbox() {
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Search suggestions functionality
function initSearchSuggestions() {
  const searchInput = document.querySelector('.search-input');
  const suggestionsContainer = document.querySelector('.search-suggestions');
  if (!searchInput || !suggestionsContainer) return;

  let debounceTimer;
  
  searchInput.addEventListener('input', function() {
    clearTimeout(debounceTimer);
    const query = this.value.trim();
    
    if (query.length < 2) {
      suggestionsContainer.innerHTML = '';
      return;
    }
    
    // Debounce to avoid too many requests
    debounceTimer = setTimeout(() => {
      fetchSuggestions(query);
    }, 300);
  });
  
  function fetchSuggestions(query) {
    // In a real app, you'd fetch from your server
    // For demo purposes, we'll use sample data
    const sampleSuggestions = [
      query + " tutorial",
      query + " examples",
      query + " documentation",
      "how to use " + query,
      "best " + query + " practices",
      query + " vs " + shuffleWord(query)
    ];
    
    displaySuggestions(sampleSuggestions);
  }
  
  function displaySuggestions(suggestions) {
    suggestionsContainer.innerHTML = '';
    
    suggestions.forEach(suggestion => {
      const item = document.createElement('div');
      item.classList.add('suggestion-item');
      item.textContent = suggestion;
      
      item.addEventListener('click', function() {
        searchInput.value = suggestion;
        suggestionsContainer.innerHTML = '';
        document.getElementById('search-form').submit();
      });
      
      suggestionsContainer.appendChild(item);
    });
  }
  
  // Helper function to shuffle a word for the "vs" suggestion
  function shuffleWord(word) {
    const alternatives = ["alternative", "competitor", "similar", "equivalent"];
    return alternatives[Math.floor(Math.random() * alternatives.length)];
  }
  
  // Close suggestions when clicking outside
  document.addEventListener('click', function(event) {
    if (!searchInput.contains(event.target) && !suggestionsContainer.contains(event.target)) {
      suggestionsContainer.innerHTML = '';
    }
  });
}

// Voice search functionality
function initVoiceSearch() {
  const voiceSearchBtn = document.querySelector('.voice-search');
  if (!voiceSearchBtn) return;
  
  // Check if browser supports SpeechRecognition
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceSearchBtn.style.display = 'none';
    return;
  }
  
  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.lang = 'en-US';
  
  voiceSearchBtn.addEventListener('click', function() {
    recognition.start();
    voiceSearchBtn.classList.add('listening');
    voiceSearchBtn.innerHTML = '<i class="fas fa-microphone-slash"></i>';
  });
  
  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript;
    document.querySelector('.search-input').value = transcript;
    
    // Submit the form after a brief delay
    setTimeout(() => {
      document.getElementById('search-form').submit();
    }, 500);
  };
  
  recognition.onend = function() {
    voiceSearchBtn.classList.remove('listening');
    voiceSearchBtn.innerHTML = '<i class="fas fa-microphone"></i>';
  };
  
  recognition.onerror = function() {
    voiceSearchBtn.classList.remove('listening');
    voiceSearchBtn.innerHTML = '<i class="fas fa-microphone"></i>';
  };
}

// Infinite scroll for image results
function initInfiniteScroll() {
  let page = 1;
  let loading = false;
  const imageResults = document.querySelector('.image-results');
  
  // Load more results when scrolling near bottom
  window.addEventListener('scroll', function() {
    if (loading) return;
    
    const scrollY = window.scrollY;
    const windowHeight = window.innerHeight;
    const documentHeight = document.documentElement.scrollHeight;
    
    // If scrolled to near bottom
    if (scrollY + windowHeight + 300 >= documentHeight) {
      loadMoreImages();
    }
  });
  
  function loadMoreImages() {
    loading = true;
    page++;
    
    // Show loading indicator
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'loading-indicator';
    loadingIndicator.innerHTML = `
      <div class="skeleton skeleton-image"></div>
      <div class="skeleton skeleton-image"></div>
      <div class="skeleton skeleton-image"></div>
    `;
    imageResults.appendChild(loadingIndicator);
    
    // Get current search query and type
    const query = new URLSearchParams(window.location.search).get('q');
    
    // Fetch more results
    fetch(`/api/search/images?q=${encodeURIComponent(query)}&page=${page}`)
      .then(response => response.json())
      .then(data => {
        // Remove loading indicator
        imageResults.removeChild(loadingIndicator);
        
        if (data.results && data.results.length > 0) {
          // Append new images to the results
          data.results.forEach(image => {
            const imageElement = createImageResult(image);
            imageResults.appendChild(imageElement);
          });
        } else {
          // No more results
          const endMessage = document.createElement('div');
          endMessage.className = 'end-message';
          endMessage.textContent = 'No more images found';
          imageResults.appendChild(endMessage);
        }
        
        loading = false;
      })
      .catch(error => {
        console.error('Error loading more images:', error);
        imageResults.removeChild(loadingIndicator);
        loading = false;
      });
  }
  
  function createImageResult(image) {
    const result = document.createElement('div');
    result.className = 'image-result fade-in';
    
    const img = document.createElement('img');
    img.src = image.thumbnail_url;
    img.alt = image.title;
    img.loading = 'lazy';
    result.appendChild(img);
    
    const info = document.createElement('div');
    info.className = 'image-info';
    info.innerHTML = `
      <div class="image-title">${image.title}</div>
      <div class="image-source">${image.domain}</div>
    `;
    result.appendChild(info);
    
    // Add click event to open the lightbox
    result.addEventListener('click', function() {
      openLightbox(image.url, image.title);
    });
    
    return result;
  }
}

// News feed carousel
function initNewsCarousel() {
  const carousel = document.querySelector('.news-carousel');
  if (!carousel) return;
  
  const prevBtn = document.querySelector('.carousel-prev');
  const nextBtn = document.querySelector('.carousel-next');
  const container = carousel.querySelector('.carousel-container');
  
  let position = 0;
  const itemWidth = 280; // Width of each news item plus margin
  const visibleItems = Math.floor(container.clientWidth / itemWidth);
  const totalItems = carousel.querySelectorAll('.news-item').length;
  
  // Hide prev button initially
  prevBtn.classList.add('hidden');
  
  // Show/hide buttons based on position
  function updateButtons() {
    prevBtn.classList.toggle('hidden', position === 0);
    nextBtn.classList.toggle('hidden', position >= totalItems - visibleItems);
  }
  
  // Move carousel
  function moveCarousel(direction) {
    if (direction === 'prev' && position > 0) {
      position--;
    } else if (direction === 'next' && position < totalItems - visibleItems) {
      position++;
    }
    
    container.style.transform = `translateX(-${position * itemWidth}px)`;
    updateButtons();
  }
  
  // Add event listeners
  if (prevBtn) prevBtn.addEventListener('click', () => moveCarousel('prev'));
  if (nextBtn) nextBtn.addEventListener('click', () => moveCarousel('next'));
  
  // Update on window resize
  window.addEventListener('resize', () => {
    const newVisibleItems = Math.floor(container.clientWidth / itemWidth);
    if (newVisibleItems !== visibleItems && position > totalItems - newVisibleItems) {
      position = Math.max(0, totalItems - newVisibleItems);
      container.style.transform = `translateX(-${position * itemWidth}px)`;
    }
    updateButtons();
  });
}

// Quick answer feature
function initQuickAnswers() {
  const quickAnswerBox = document.querySelector('.quick-answer');
  if (!quickAnswerBox) return;
  
  // Add expand/collapse functionality
  const expandBtn = quickAnswerBox.querySelector('.expand-btn');
  if (expandBtn) {
    expandBtn.addEventListener('click', function() {
      quickAnswerBox.classList.toggle('expanded');
      this.innerHTML = quickAnswerBox.classList.contains('expanded') ? 
        '<i class="fas fa-chevron-up"></i>' : 
        '<i class="fas fa-chevron-down"></i>';
    });
  }
  
  // Add "Did this answer your question?" feedback
  const feedbackBtns = quickAnswerBox.querySelectorAll('.feedback-btn');
  feedbackBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      // Remove active class from all buttons
      feedbackBtns.forEach(b => b.classList.remove('active'));
      
      // Add active class to clicked button
      this.classList.add('active');
      
      // Record feedback (in a real app, send to server)
      const feedback = this.dataset.value;
      console.log(`User feedback: ${feedback}`);
      
      // Show thank you message
      const feedbackContainer = quickAnswerBox.querySelector('.feedback-container');
      feedbackContainer.innerHTML = '<span class="feedback-thanks">Thank you for your feedback!</span>';
    });
  });
}

// Focus mode toggle
function initFocusMode() {
  const focusToggle = document.querySelector('.focus-mode-toggle');
  if (!focusToggle) return;
  
  // Check if focus mode was previously enabled
  const focusModeEnabled = localStorage.getItem('focusMode') === 'true';
  if (focusModeEnabled) {
    document.body.classList.add('focus-mode');
    focusToggle.classList.add('focus-mode-active');
  }
  
  focusToggle.addEventListener('click', function() {
    document.body.classList.toggle('focus-mode');
    this.classList.toggle('focus-mode-active');
    
    // Save preference
    const isActive = document.body.classList.contains('focus-mode');
    localStorage.setItem('focusMode', isActive);
  });
}

// Time filter functionality
function initTimeFilter() {
  const timeFilter = document.querySelector('.time-filter');
  if (!timeFilter) return;
  
  const yearSlider = timeFilter.querySelector('.year-slider');
  if (!yearSlider) return;
  
  // Update display and filter results when slider changes
  yearSlider.addEventListener('change', function() {
    const yearDisplay = timeFilter.querySelector('.year-display');
    if (yearDisplay) yearDisplay.textContent = this.value;
    
    // Add as form parameter and submit
    const searchForm = document.getElementById('search-form');
    const timeInput = document.getElementById('time-filter-input');
    if (searchForm && timeInput) {
      timeInput.value = this.value;
      searchForm.submit();
    }
  });
  
  // Show the current value on load
  const yearDisplay = timeFilter.querySelector('.year-display');
  if (yearDisplay && yearSlider) {
    yearDisplay.textContent = yearSlider.value;
  }
}

// Related searches
function initRelatedSearches() {
  const relatedItems = document.querySelectorAll('.related-item');
  
  relatedItems.forEach(item => {
    item.addEventListener('click', function() {
      const query = this.textContent.trim();
      const searchInput = document.querySelector('.search-input');
      
      if (searchInput) {
        searchInput.value = query;
        document.getElementById('search-form').submit();
      }
    });
  });
}

// Initialize all features when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  initTheme();
  initSearchTabs();
  initLightbox();
  initSearchSuggestions();
  initVoiceSearch();
  initNewsCarousel();
  initQuickAnswers();
  initFocusMode();
  initTimeFilter();
  initRelatedSearches();
  
  // Initialize infinite scroll for image results
  if (document.querySelector('.image-results')) {
    initInfiniteScroll();
  }
});