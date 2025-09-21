import { ref } from "vue"
import { auth, createUserWithEmailAndPassword } from '../firebase/config.ts'

export function useSignup() {
    const error = ref(null);
    const isPending = ref(false);
    
    const signup = async (email: string, password: string, displayName: string) => {
        error.value = null;
        isPending.value = true;
    
        try {
            console.log(auth)
            const res = await createUserWithEmailAndPassword(auth, email, password)
            if (!res) {
                throw new Error('Cloud not complete the signup')
            }
            //await res.user.updateProfile({displayName})
            console.log(res.user)
            isPending.value = false
            error.value = null
            return res
    
        } catch(err: any) {
            console.log(err.message)
            error.value = err.message
            isPending.value = false
        }
    }

    return { error, signup, isPending }
}

export default useSignup
