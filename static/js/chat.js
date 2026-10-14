function openChat(){

document.getElementById("aiChat").style.display="flex";

}

function closeChat(){

document.getElementById("aiChat").style.display="none";

}

async function sendMessage(){

    let input=document.getElementById("userMessage");

    let msg=input.value.trim();

    if(msg=="") return;

    let body=document.getElementById("chatBody");

    body.innerHTML+=`
    <div style="text-align:right;margin-top:15px;">
        <span style="
            background:#4f46e5;
            color:white;
            padding:10px;
            border-radius:10px;
            display:inline-block;
            max-width:80%;">
            ${msg}
        </span>
    </div>
    `;

    input.value="";

    body.innerHTML+=`
    <div id="typing" style="margin-top:15px;">
        🤖 <i>Thinking...</i>
    </div>
    `;

    body.scrollTop=body.scrollHeight;

    const formData=new FormData();

    formData.append("message",msg);

    const response=await fetch("/askAI",{
        method:"POST",
        body:formData
    });

    const data=await response.json();
    // ===============================
// AI ACTION CENTER
// ===============================

if(data.action=="billing"){

    setTimeout(()=>{

        window.location="/billing";

    },1000);

}

else if(data.action=="products"){

    setTimeout(()=>{

        window.location="/productList";

    },1000);

}

else if(data.action=="reports"){

    setTimeout(()=>{

        window.location="/reports";

    },1000);

}

else if(data.action=="dashboard"){

    setTimeout(()=>{

        window.location="/dashboard";

    },1000);

}

else if(data.action=="deadstock"){

    setTimeout(()=>{

        window.location="/deadStock";

    },1000);

}

else if(data.action=="prediction"){

    setTimeout(()=>{

        window.location="/prediction";

    },1000);

}

else if(data.action=="saleshistory"){

    setTimeout(()=>{

        window.location="/salesHistory";

    },1000);

}

else if(data.action=="logout"){

    setTimeout(()=>{

        window.location="/logout";

    },1000);

}

    document.getElementById("typing").remove();

    body.innerHTML+=`
    <div style="margin-top:15px;">
        <span style="
            background:#f1f5f9;
            padding:12px;
            border-radius:10px;
            display:inline-block;
            max-width:90%;
            white-space:pre-wrap;">
            🤖 ${data.reply}
        </span>
    </div>
    `;

    body.scrollTop=body.scrollHeight;

}

document.addEventListener("DOMContentLoaded",()=>{

    document.getElementById("userMessage").addEventListener("keypress",function(e){

        if(e.key==="Enter"){

            e.preventDefault();

            sendMessage();

        }

    });

});
function openOCR(){

    window.location.href="/purchaseOCR";

}