<template>
    <header
        data-test="header"
        id="website-header"
        class="header w-full bg-white shadow-5 overflow-hidden sticky top-0"
        style="z-index: 500;"
        tabindex="-1">
        <div class="grid">
            <a href="#page" class="hidden">
                Skip to Content
            </a>
            <!-- Background -->
            <div class="flex col-12 pb-0">
                <!-- Title and nav wrapper -->
                <div class="col-3" style="min-width: 15em;">
                    <div class="header-title mt-2" data-animation-role="header-element">
                        <div class="header-title-logo">
                            <a href="/" data-animation-role="header-element">
                                <img
                                src="/src/assets/images/iCofnitionLogo-website.png?format=1500w"
                                alt="iCognition.ai">
                            </a>
                        </div>
                    </div>
                </div>
                <div class="col-6 text-center flex align-content-center flex-wrap"></div>

                <!-- Actions -->
                <div class="col-3 md:flex pr-3 align-items-center justify-content-end">
                    <div class="hidden md:flex website-login-logout">
                        <div v-if="authStore.isAuthenticated" class="text-right">
                            <button type="button" class="login-with-google-btn mr-2" @click="handleLogout">
                                Logout
                            </button>
                        </div>
                        <div v-else class="text-right">
                            <button type="button" class="login-with-google-btn mr-2" @click="handleGoogleLogin">
                                Sign in with Google
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </header>
    <header
        data-test="header"
        id="app-header"
        class="header w-full bg-primary-800 shadow-5 sticky top-0"
        style="z-index: 1000;"
        tabindex="-1">
        <div class="grid">
            <div class="flex col-12 pb-0">
                <!-- Logo section -->
                <div class="col-3 py-1" style="min-width: 9.5em;">
                    <div class="header-title app-header-title mt-2" data-animation-role="header-element">
                        <div class="header-title-logo">
                            <a href="/" data-animation-role="header-element">
                                <img
                                src="/src/assets/images/iCognitionLogo.png?format=1500w"
                                alt="iCognition.ai">
                            </a>
                        </div>
                    </div>
                </div>
                
                <!-- Center tabs section -->
                <div class="col-6 text-center py-1 flex align-content-center flex-wrap">
                    <div class="app-header-routing flex flex-row text-white" data-animation-role="header-element">
                        <p :class="[router.currentRoute.value.name == 'library' || router.currentRoute.value.name == 'docxray' ? 'selectedRoute': '']" class="mr-3 text-lg cursor-pointer text-400" @click="router.push('/library')">My Library</p>
                        <p :class="[router.currentRoute.value.name == 'collections' || router.currentRoute.value.name == 'collectiondetails' ? 'selectedRoute': '']" class="mr-3 text-lg cursor-pointer text-400" @click="router.push('/collections')" >My Collections</p>
                    </div>
                </div>

                <!-- Actions section -->
                <div class="col-3 md:flex pr-3 py-1 align-items-center justify-content-end">
                    <div class="hidden md:flex website-login-logout">
                        <div v-if="authStore.isAuthenticated" class="text-right">
                            <button type="button" class="login-with-google-btn mr-2" @click="handleLogout">
                                Logout
                            </button>
                        </div>
                        <div v-else class="text-right">
                            <button type="button" class="login-with-google-btn mr-2" @click="handleGoogleLogin">
                                Sign in with Google
                            </button>
                        </div>
                    </div>
                    <div class="card pl-2 py-4 justify-content-end flex md:hidden webite-login-menu">
                        <Button type="button" class="bg-primary text-white" @click="toggleWebsiteMenu" icon="pi pi-user" aria-haspopup="true" aria-controls="overlay_menu" />
                        <Menu ref="menu_website" id="overlay_menu" :model="website_menu_items" :popup="true" />
                    </div>
                    <div class="card px-4 py-0 flex justify-content-end app-profile" style="position: relative;">
                        <div @click="toggleAppMenu" class="flex flex-row align-items-center cursor-pointer" style="position: relative;">
                            <img v-if="authStore.currentUser?.photoURL" 
                                 :src="authStore.currentUser.photoURL" 
                                 alt="User Avatar" 
                                 class="border-circle mr-2" 
                                 style="width: 32px; height: 32px;" />
                            <div v-else class="bg-primary border-circle mr-2 flex align-items-center justify-content-center" 
                                 style="width: 32px; height: 32px;">
                                <i class="pi pi-user text-white"></i>
                            </div>
                            <p class="text-white ml-2">{{ authStore.currentUser?.displayName }}</p>
                            <i class="pi pi-angle-down text-white ml-2 mt-1"></i>
                        </div>
                        
                        <!-- Simple dropdown menu -->
                        <div v-if="showAppMenu" 
                             @click.stop
                             class="absolute bg-white border-round shadow-3 p-2"
                             style="top: 100%; right: 0; min-width: 150px; z-index: 9999; border: 1px solid #e0e0e0;">
                            <div @click="handleLogout" 
                                 class="p-2 cursor-pointer border-round flex align-items-center text-gray-700"
                                 style="transition: background-color 0.2s;"
                                 @mouseover="$event.target.style.backgroundColor = '#f5f5f5'"
                                 @mouseout="$event.target.style.backgroundColor = 'transparent'">
                                <i class="pi pi-sign-out mr-2"></i>
                                Sign Out
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </header>
</template>

<script lang="ts">
    export default {
        name: 'Navbar'
    }
</script>

<script setup lang="ts">
    import { useAuthStore } from '../stores/auth_store.js';
    import { useRouter } from 'vue-router';
    import { ref, onMounted, onUnmounted, nextTick } from 'vue';
    import Button from 'primevue/button';
    import Menu from 'primevue/menu';
    import Menubar from 'primevue/menubar';
    import TabMenu from 'primevue/tabmenu';

    const authStore = useAuthStore();
    const menu_website = ref();
    const showAppMenu = ref(false);
    const router = useRouter();

    const toggleAppMenu = (event: Event) => {
        event.stopPropagation();
        showAppMenu.value = !showAppMenu.value;
        console.log('Toggle app menu:', showAppMenu.value);
    };

    const toggleWebsiteMenu = (event: Event) => {
        menu_website.value.toggle(event);
    };

    // Close menu when clicking outside
    const closeMenu = () => {
        showAppMenu.value = false;
    };

    // Clean up function
    const cleanup = () => {
        showAppMenu.value = false;
        document.removeEventListener('click', closeMenu);
    };

    onMounted(() => {
        document.addEventListener('click', closeMenu);
    });

    onUnmounted(() => {
        cleanup();
    });

    // Note: Navigation is now handled by router guards, not component watchers

    const handleLogout = async () => {
        console.log('Starting logout process...');
        showAppMenu.value = false; // Close menu first
        
        try {
            await authStore.logout();
            console.log('Logout successful, navigating to home...');
            
            // Use nextTick to ensure DOM is stable before navigation
            await nextTick();
            await router.push('/');
            
            console.log('Navigation completed');
        } catch (error: any) {
            console.error('Logout error:', error);
        }
    }

    const handleGoogleLogin = async () => {
        try {
            await authStore.loginWithGoogle();
            console.log('Login successful using Google:', authStore.currentUser);
            
            // Navigate to library after successful login
            console.log('Redirecting to library after login...');
            await nextTick();
            await router.push('/library');
            console.log('Navigation to library completed');
        } catch (error: any) {
            console.error('Login failed using Google:', error);
        }
    }

    const handleAccount = async () => { }

    const handleNotifications = async () => { }

    const app_menu_items = ref([
        // {
        //     label: ' Notifications',
        //     icon: 'pi pi-envelope',
        //     badge: 2,
        //     command: () => {
        //         handleNotifications();
        //     }
        // },
        // {
        //     label: ' Account',
        //     icon: 'pi pi-cog',
        //     command: () => {
        //         handleAccount();
        //     }
        // },
        {
            label: ' Sign Out',
            icon: 'pi pi-sign-out',
            command: () => {
                handleLogout();
            }
        }
    ]);

    let website_menu_items = ref([
        {
            label: ' Login with Google',
            icon: 'pi pi-google',
            command: () => {
                handleGoogleLogin();
            }
        }
    ]);

    router.afterEach((to, from) => {
        if (to.name == undefined || to.name == 'home' || to.name == '404') {
            document.body.classList.remove('route-app');
            document.body.classList.add('route-website');
            document.getElementById('website-header')?.classList.remove('hidden');
            document.getElementById('app-header')?.classList.add('hidden');
        } else {
            document.body.classList.remove('route-website');
            document.body.classList.add('route-app');
            document.getElementById('website-header')?.classList.add('hidden');
            document.getElementById('app-header')?.classList.remove('hidden');
        }
    });

    const tabItems = ref([
        { label: 'My Library', route: '/library' },
        { label: 'My Collections', route: '/collections' }
    ]);

    const activeTabIndex = ref(0);

    const syncActiveTab = () => {
        const name = router.currentRoute.value.name as string | undefined;
        activeTabIndex.value = name === 'collections' || name === 'collectiondetails' ? 1 : 0;
    };

    const onTabChange = (e: any) => {
        const item = tabItems.value[e.index];
        if (item?.route) router.push(item.route);
    };

    onMounted(() => {
        syncActiveTab();
    });
</script>