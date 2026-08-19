async function expect(response){if(!response.ok){let message=`Request failed (${response.status})`;try{const body=await response.json();message=body.message||body.detail||message}catch{}throw new Error(message)}return response.json()}
export async function uploadImage(file){const data=new FormData();data.append('file',file);return expect(await fetch('/api/images/upload',{method:'POST',body:data}))}
export async function createAnalysis(originalId,enhancedId){return expect(await fetch('/api/analyses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({original_image_id:originalId,enhanced_image_id:enhancedId})}))}
export async function getAnalysis(id){return expect(await fetch(`/api/analyses/${id}`))}
export async function getDatasets(){return expect(await fetch('/api/datasets'))}
export async function attachReference(id,datasetId){return expect(await fetch(`/api/analyses/${id}/reference`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:datasetId})}))}
export async function verifyPhysical(id,mission){return expect(await fetch(`/api/analyses/${id}/verify`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mission_profile:mission})}))}
export async function saveAlignment(id,imagePoints,referencePoints){return expect(await fetch(`/api/analyses/${id}/align`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_points:imagePoints,reference_points:referencePoints})}))}
export async function requestExport(id){return expect(await fetch(`/api/analyses/${id}/export`,{method:'POST'}))}
export async function getPassport(id){return expect(await fetch(`/api/analyses/${id}/passport`))}
