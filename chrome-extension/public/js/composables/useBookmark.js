import { ref } from 'vue'
import { Endpoints, base_url } from './envVar.js'

const postBookmark = (url) => {
    const bookmark = ref(null)
    const error = ref(null)

    const load = async () => {
        try {
            let data = await fetch(`${base_url}${Endpoints.bookmark}`, {
                method: 'post',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                }),
            })
            if (!data.ok) {
                throw Error('That bookmark does not exist')
            }
            bookmark.value = await data.json()
        }
        catch (err) {
            error.value = err.message
        }
    }

    return { bookmark, error, load }    
}

export default postBookmark