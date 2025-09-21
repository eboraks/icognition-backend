export function handleFileUpload(event: any, user_id: string) {

    const baseurl = import.meta.env.VITE_APP_API_BASE_URL;
    const formData = new FormData();
    formData.append('file', event.files[0], event.files[0].name); 
    formData.append('user_id', user_id); 

    console.log('Uploading file...');

    fetch(`${baseurl}/create_source_upload_file/`, {
      method: 'POST',
      body: formData,
      headers: {
        'accept': 'application/json',
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      // Handle successful upload response
      console.log(data); 
    })
    .catch(error => {
      // Handle upload error
      console.error('Upload failed:', error);
    });
  }