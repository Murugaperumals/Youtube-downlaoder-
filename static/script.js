function getVideo() {
    const url = document.getElementById('urlInput').value;
    if (!url) return;
    
    document.getElementById('urlHidden').value = url;
    
    // Fetch video info
    fetch('/api/video-info', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url: url })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }
        
        // Update thumbnail
        const thumb = document.querySelector('.video-thumb');
        if (data.thumbnail) {
            thumb.style.backgroundImage = 'url(' + data.thumbnail + ')';
            thumb.style.backgroundSize = 'cover';
            thumb.style.backgroundPosition = 'center';
        }
        
        // Update title and description
        document.getElementById('videoTitle').textContent = data.title || '';
        document.getElementById('videoDesc').textContent = data.description || '';
        
        // Show video info and options
        document.getElementById('videoInfo').classList.add('show');
        document.getElementById('downloadOptions').classList.add('show');
    })
    .catch(error => {
        alert('Error fetching video: ' + error.message);
    });
}

function downloadQuality(quality) {
    const url = document.getElementById('urlInput').value;
    const audioOnly = document.getElementById('audio_only').checked;
    const subsOnly = document.getElementById('subs_only').checked;
    
    if (!url) {
        alert('Please enter a URL first');
        return;
    }
    
    // Show downloading message
    alert('Downloading... Please wait. Your browser will download the file automatically.');
    
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/';
    form.style.display = 'none';
    
    const urlInput = document.createElement('input');
    urlInput.type = 'hidden';
    urlInput.name = 'url';
    urlInput.value = url;
    form.appendChild(urlInput);
    
    const qualityInput = document.createElement('input');
    qualityInput.type = 'hidden';
    qualityInput.name = 'quality';
    qualityInput.value = quality;
    form.appendChild(qualityInput);
    
    if (audioOnly) {
        const audioInput = document.createElement('input');
        audioInput.type = 'hidden';
        audioInput.name = 'audio_only';
        audioInput.value = 'on';
        form.appendChild(audioInput);
    }
    
    if (subsOnly) {
        const subsInput = document.createElement('input');
        subsInput.type = 'hidden';
        subsInput.name = 'subs_only';
        subsInput.value = 'on';
        form.appendChild(subsInput);
    }
    
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
}

function showProgress() {
    document.getElementById('progress').style.display = 'block';
}
