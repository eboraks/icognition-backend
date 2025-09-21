import { ref } from "vue"
import { auth } from '../firebase/config.ts'
import user_state from "./getUser.ts"

export function useLogout() {
    const error = ref(null);
    const isPending = ref(false);

    const logout = async () => {
        error.value = null
        isPending.value = true
        
        try {
            await auth.signOut()
            isPending.value = false
            user_state.user = null
        } catch (err: any) {
            console.log(err.message)
            error.value = err.message
            isPending.value = false
        }
    }

    return { error, logout, isPending}
}
