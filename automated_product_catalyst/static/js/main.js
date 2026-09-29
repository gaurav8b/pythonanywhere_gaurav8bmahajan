// --- DOM Elements & State ---
const dom = {
    fileUpload: document.getElementById('file-upload'),
    fileDropZone: document.getElementById('file-drop-zone'),
    fileUploadText: document.getElementById('file-upload-text'),
    imagePreviewContainer: document.getElementById('image-preview-container'),
    generateBtn: document.getElementById('generate-btn'),
    pipelineStatusCard: document.getElementById('pipeline-status-card'),
    resultsContainer: document.getElementById('results-container'),
    status: {
        text: document.getElementById('status-text'),
        image: document.getElementById('status-image'),
        video: document.getElementById('status-video'),
        distribution: document.getElementById('status-distribution'),
    },
    assetCards: {
        text: document.getElementById('text-asset-card'),
        image: document.getElementById('image-asset-card'),
        video: document.getElementById('video-asset-card'),
        distribution: document.getElementById('distribution-card'),
    },
    outputs: {
        title: document.getElementById('product-title'),
        description: document.getElementById('product-description'),
        cutout: document.getElementById('image-cutout'),
        lifestyle: document.getElementById('image-lifestyle'),
        videoKeyframe: document.getElementById('video-keyframe'),
        videoScriptOverlay: document.getElementById('video-script-overlay'),
        threeDContainer: document.getElementById('3d-container'),
    }
};

let imageFile = null;
let renderer, scene, camera, cube; // For 3D

// --- Event Listeners ---
dom.fileUpload.addEventListener('change', (e) => handleFile(e.target.files[0]));
dom.generateBtn.addEventListener('click', runFullPipeline);

// --- UI & State Management ---
function handleFile(file) {
    if (!file || !['image/jpeg', 'image/png'].includes(file.type)) return;
    imageFile = { name: file.name, dataUrl: URL.createObjectURL(file), mimeType: file.type, blob: file };
    dom.imagePreviewContainer.innerHTML = `<img src="${imageFile.dataUrl}" class="rounded-lg w-full h-auto">`;
    dom.generateBtn.disabled = false;
}

function setStatus(stage, status, text) {
    const el = dom.status[stage];
    const dot = el.querySelector('.status-dot');
    const statusText = el.querySelector('span:last-child');
    dot.className = `status-dot mr-3 status-${status}`;
    statusText.textContent = text;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// --- 3D Model Setup ---
function init3D() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe5e7eb);
    camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(dom.outputs.threeDContainer.clientWidth, dom.outputs.threeDContainer.clientHeight);
    dom.outputs.threeDContainer.appendChild(renderer.domElement);

    const geometry = new THREE.BoxGeometry();
    const material = new THREE.MeshStandardMaterial({ color: 0x60a5fa });
    cube = new THREE.Mesh(geometry, material);
    scene.add(cube);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 10, 7.5);
    scene.add(directionalLight);

    camera.position.z = 2;

    function animate() {
        requestAnimationFrame(animate);
        cube.rotation.x += 0.005;
        cube.rotation.y += 0.005;
        renderer.render(scene, camera);
    }
    animate();
}

// --- The Main Orchestration Pipeline ---
async function runFullPipeline() {
    if (!imageFile) return;

    // 1. Initialize UI
    dom.generateBtn.disabled = true;
    dom.generateBtn.textContent = 'Engine Running...';
    dom.pipelineStatusCard.classList.remove('hidden');
    dom.resultsContainer.classList.remove('hidden');
    Object.values(dom.assetCards).forEach(c => c.classList.add('hidden'));


    // 2. Stage 1: Textual Assets
    setStatus('text', 'running', 'Generating...');
    const textContent = await generateTextAssets();
    if (!textContent) { setStatus('text', 'pending', 'Failed'); return; }
    dom.outputs.title.textContent = textContent.productName;
    dom.outputs.description.textContent = textContent.productDescription;
    dom.assetCards.text.classList.remove('hidden');
    dom.assetCards.text.classList.add('fade-in');
    setStatus('text', 'complete', 'Done');
    await sleep(1000);

    // 3. Stage 2: Image Assets
    setStatus('image', 'running', 'Generating...');
    const imageContent = await generateImageAssets(textContent);
    if (!imageContent) { setStatus('image', 'pending', 'Failed'); return; }
    dom.outputs.cutout.src = imageContent.cutoutUrl;
    dom.outputs.lifestyle.src = imageContent.lifestyleUrl;
    dom.assetCards.image.classList.remove('hidden');
    dom.assetCards.image.classList.add('fade-in');
    setStatus('image', 'complete', 'Done');
    await sleep(1000);

    // 4. Stage 3: Video & 3D Assets
    setStatus('video', 'running', 'Generating...');
    await generateVideoAssets(textContent, imageContent.lifestyleUrl);
    init3D();
    dom.assetCards.video.classList.remove('hidden');
    dom.assetCards.video.classList.add('fade-in');
    setStatus('video', 'complete', 'Done');
    await sleep(1000);

    // 5. Stage 4: Distribution
    setStatus('distribution', 'running', 'Packaging...');
    await sleep(1500); // Simulate packaging
    dom.assetCards.distribution.classList.remove('hidden');
    dom.assetCards.distribution.classList.add('fade-in');
    setStatus('distribution', 'complete', 'Ready');

    dom.generateBtn.textContent = 'Run Again';
    dom.generateBtn.disabled = false;
}

// --- API & Processing Functions ---

async function makeGeminiRequest(prompt, schema) {
    const apiKey = ""; // Canvas will provide
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`;
    const payload = {
        contents: [{ role: "user", parts: [ { text: prompt } ] }],
        generationConfig: { responseMimeType: "application/json", responseSchema: schema }
    };
    if (imageFile) {
        const base64Data = await blobToBase64(imageFile.blob);
        payload.contents[0].parts.push({ inlineData: { mimeType: imageFile.mimeType, data: base64Data } });
    }
    try {
        const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) throw new Error(`API Error: ${res.status}`);
        const data = await res.json();
        return JSON.parse(data.candidates[0].content.parts[0].text);
    } catch (e) { console.error("Gemini request failed", e); return null; }
}

async function makeImagenRequest(prompt) {
    const apiKey = ""; // Canvas will provide
    const url = `https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key=${apiKey}`;
    const payload = { instances: [{ prompt }], parameters: { "sampleCount": 1 } };
     try {
        const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) throw new Error(`API Error: ${res.status}`);
        const data = await res.json();
        return `data:image/png;base64,${data.predictions[0].bytesBase64Encoded}`;
    } catch (e) { console.error("Imagen request failed", e); return null; }
}

async function generateTextAssets() {
    const prompt = `Analyze the product in the image. Generate a short, catchy product name. Then, write a compelling product description using the AIDA framework (Attention, Interest, Desire, Action).`;
    const schema = { type: "OBJECT", properties: { productName: { "type": "STRING" }, productDescription: { "type": "STRING" } } };
    return await makeGeminiRequest(prompt, schema);
}

async function generateImageAssets(textContent) {
    // 1. Remove Background
    const cutoutBlob = await backgroundRemoval.removeBackground(imageFile.dataUrl);
    const cutoutUrl = URL.createObjectURL(cutoutBlob);

    // 2. Generate Lifestyle Scene
    const prompt = `Based on the product named "${textContent.productName}", generate a detailed, photorealistic prompt for an image generation model to create a suitable background scene. For example, for a coffee maker, suggest 'A modern sunlit kitchen counter'.`;
    const schema = { type: "OBJECT", properties: { scenePrompt: { "type": "STRING" } } };
    const sceneResult = await makeGeminiRequest(prompt, schema);
    if (!sceneResult) return null;

    const lifestyleUrl = await makeImagenRequest(sceneResult.scenePrompt);
    if (!lifestyleUrl) return null;

    // 3. Composite product onto lifestyle image
    const finalImageUrl = await compositeImages(lifestyleUrl, cutoutUrl);

    return { cutoutUrl, lifestyleUrl: finalImageUrl };
}

async function generateVideoAssets(textContent, lifestyleUrl) {
    // 1. Generate Script
    const prompt = `For the product "${textContent.productName}", generate a 3-scene script for a 15-second video ad. Each scene should be a short, descriptive sentence.`;
    const schema = { type: "OBJECT", properties: { scene1: { "type": "STRING" }, scene2: { "type": "STRING" }, scene3: { "type": "STRING" } } };
    const script = await makeGeminiRequest(prompt, schema);
    if (!script) return null;

    // 2. Simulate video by showing keyframes
    const scenes = [script.scene1, script.scene2, script.scene3];
    dom.outputs.videoKeyframe.src = lifestyleUrl;

    for (let i = 0; i < scenes.length * 2; i++) { // Loop to show each scene for a bit
        const sceneIndex = i % scenes.length;
        dom.outputs.videoScriptOverlay.textContent = scenes[sceneIndex];
        await sleep(2500); // 15s / 6 keyframes = 2.5s per frame
    }
    dom.outputs.videoScriptOverlay.textContent = `Buy the ${textContent.productName} today!`;
}

// --- UTILITIES ---
function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

function compositeImages(backgroundUrl, foregroundUrl) {
    return new Promise((resolve, reject) => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const bg = new Image();
        bg.crossOrigin = "Anonymous";
        bg.onload = () => {
            canvas.width = bg.width;
            canvas.height = bg.height;
            ctx.drawImage(bg, 0, 0);

            const fg = new Image();
            fg.crossOrigin = "Anonymous";
            fg.onload = () => {
                const scale = Math.min(1, (canvas.width * 0.7) / fg.width, (canvas.height * 0.7) / fg.height);
                const w = fg.width * scale;
                const h = fg.height * scale;
                const x = (canvas.width - w) / 2;
                const y = (canvas.height - h) / 2;
                ctx.drawImage(fg, x, y, w, h);
                resolve(canvas.toDataURL('image/png'));
            };
            fg.onerror = reject;
            fg.src = foregroundUrl;
        };
        bg.onerror = reject;
        bg.src = backgroundUrl;
    });
}
