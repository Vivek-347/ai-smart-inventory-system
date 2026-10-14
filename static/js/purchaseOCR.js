const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("billInput");
const browseBtn = document.getElementById("browseBtn");

const previewArea = document.getElementById("previewArea");
const loader = document.getElementById("loader");

const progressSection = document.querySelector(".progress-section");
const progressBar = document.getElementById("progressBar");

const uploadForm = document.getElementById("uploadForm");

// ============================
// Browse Button
// ============================

browseBtn.addEventListener("click", function () {

    fileInput.click();

});

// ============================
// File Selected
// ============================

fileInput.addEventListener("change", function () {

    showPreview(this.files[0]);

});

// ============================
// Drag Enter
// ============================

dropZone.addEventListener("dragover", function (e) {

    e.preventDefault();

    dropZone.style.borderColor = "#10b981";
    dropZone.style.background = "#ecfdf5";

});

// ============================
// Drag Leave
// ============================

dropZone.addEventListener("dragleave", function () {

    dropZone.style.borderColor = "#4f46e5";
    dropZone.style.background = "#f8fafc";

});

// ============================
// Drop File
// ============================

dropZone.addEventListener("drop", function (e) {

    e.preventDefault();

    dropZone.style.borderColor = "#4f46e5";
    dropZone.style.background = "#f8fafc";

    const file = e.dataTransfer.files[0];

    fileInput.files = e.dataTransfer.files;

    showPreview(file);

});

// ============================
// Preview Function
// ============================

function showPreview(file){

    if(!file) return;

    previewArea.style.display = "block";

    if(file.type.includes("image")){

        previewArea.innerHTML = `

            <img src="${URL.createObjectURL(file)}">

            <h5 class="mt-3">
                ${file.name}
            </h5>

            <p class="text-success">

                ✔ Image Ready

            </p>

        `;

    }

    else{

        previewArea.innerHTML = `

            <div class="pdf-preview">

                <i class="bi bi-file-earmark-pdf-fill"></i>

                <h4 class="mt-3">

                    ${file.name}

                </h4>

                <p>

                    PDF Ready for AI OCR

                </p>

            </div>

        `;

    }

}

// ============================
// Upload Animation
// ============================

uploadForm.addEventListener("submit", function(e){

    if(fileInput.files.length==0){

        e.preventDefault();

        alert("Please Select Invoice.");

        return;

    }

    progressSection.style.display="block";

    loader.style.display="block";

    document.getElementById("uploadBtn").disabled=true;

    let progress=0;

    const interval=setInterval(function(){

        progress+=5;

        progressBar.style.width=progress+"%";

        progressBar.innerHTML=progress+"%";

        if(progress>=100){

            clearInterval(interval);

        }

    },120);

});

// ============================
// Drop Zone Click
// ============================

dropZone.addEventListener("click",function(){

    fileInput.click();

});

// ============================
// Hover Effect
// ============================

dropZone.addEventListener("mouseenter",function(){

    dropZone.style.transform="scale(1.02)";

});

dropZone.addEventListener("mouseleave",function(){

    dropZone.style.transform="scale(1)";

});