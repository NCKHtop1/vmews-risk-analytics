async function generate(){
 const ticker=document.getElementById('ticker').value;
 const from=document.getElementById('from').value;
 const to=document.getElementById('to').value;
 document.getElementById('status').innerText='Processing '+ticker+' '+from+'-'+to+'...';
 // API connector will be attached to backend engine
}
