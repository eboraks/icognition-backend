// Function that makes http request to get library data
import { StudyCollection } from '@/components/models/StudyCollection.ts';
import { ref } from 'vue';

export function useStudyCollection() {
    
    const relatedEntitites = ref();
    const candidateDocs = ref();
    const studyCollection = ref(new StudyCollection('', '', ''));
    const studyCollections = ref();
    const errorStudyCollection = ref(null)
    const isPendingStudyCollection = ref(false)
    const searchResult = ref<null | string>(null);
    
    const base_url = import.meta.env.VITE_APP_API_BASE_URL
    console.log("Base URL: ", base_url)

    const getStudyCollections = async (user_id: string) => {
        errorStudyCollection.value = null
        isPendingStudyCollection.value = true
        try {
            const url = `${base_url}/study_collections/${user_id}`
            console.log("URL: ", url)
            const res = await fetch(url)
            if (!res.ok) {
                throw Error('Could not fetch the data for that resource')
            }
            studyCollections.value = await res.json();
            console.log("Study Collections: ", studyCollections.value);
            isPendingStudyCollection.value = false
        } catch (err: any) {
            console.error(err)
            errorStudyCollection.value = err.message
            isPendingStudyCollection.value = false
            console.log("Error: ", errorStudyCollection.value)
        }
    }

    const getStudyCollection = async (id: string) => {
        errorStudyCollection.value = null
        isPendingStudyCollection.value = true
        try {
            const url = `${base_url}/study_collection/${id}`
            console.log("URL: ", url)
            const res = await fetch(url)
            if (!res.ok) {
                throw Error('Could not fetch the data for that resource')
            }
            studyCollection.value = await res.json();
            console.log("Study Collection: ", studyCollection.value);
            isPendingStudyCollection.value = false
        } catch (err: any) {
            console.error(err)
            errorStudyCollection.value = err.message
            isPendingStudyCollection.value = false
            console.log("Error: ", errorStudyCollection.value)
        }
    }

    const getRelatedEntities = async (project_id: string) => {
        errorStudyCollection.value = null
        isPendingStudyCollection.value = true
        try {
            const url = `${base_url}/study_collection/${project_id}/related_entities`
            console.log("URL: ", url)
            const res = await fetch(url)
            if (!res.ok) {
                throw Error('Could not fetch the data for that resource')
            }
            relatedEntitites.value = await res.json();
            console.log("Study Collection: ", relatedEntitites);
            isPendingStudyCollection.value = false
        } catch (err: any) {
            console.error(err)
            errorStudyCollection.value = err.message
            isPendingStudyCollection.value = false
            console.log("Error: ", errorStudyCollection.value)
        }
    }

    const getCandidatesDocs = async (project_id: string) => {
        errorStudyCollection.value = null
        isPendingStudyCollection.value = true
        try {
            const url = `${base_url}/study_collection/${project_id}/candidate_documents`
            const res = await fetch(url)
            if (!res.ok) {
                throw Error(`Could not fetch the data for that resource: ${url}`)
            }
            candidateDocs.value = await res.json();
            isPendingStudyCollection.value = false;
        } catch (err: any) {
            console.error(err)
            errorStudyCollection.value = err.message;
            isPendingStudyCollection.value = false;
            console.log("Error: ", errorStudyCollection.value)
        }
    }

    // Post a study Collection
    async function postStudyCollection(study_collection: StudyCollection) {
        try {
            await fetch(`${base_url}/study_collection`, {
                method: 'post',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(study_collection)
            }).then(response => {
                console.log('postStudyCollection -> response: ', response)
                if (response.status == 200) {
                    let studyCollection = response.json() as any;
                    console.log(`postStudyCollection accepted, seding id ${studyCollection.id} to render Study Collection`);
                }
            }).catch (err => {
                console.log('postStudyCollection -> error: ', err);
            })
            
        } catch (err) {
            console.log('postStudyCollection -> error: ', err);
        }
    }

    const postCollectionDocumentLink = async (study_collection_id: string, documents_ids: [string]) => {

        console.log('postCollectionDocumentLink -> project_document: ')
        //Fetch post with request.project_document
        try {
            let response = await fetch(`${base_url}/study_collection/${study_collection_id}/documents`, {
                method: 'put',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(documents_ids)
            })
            
            console.log('postCollectionDocumentLink -> response: ', response)
            if (response.status == 202) {
                let projectDocumentLink = await response.json()
                console.log(`postCollectionDocumentLink accepted. Response: ${projectDocumentLink}`)
            }
        } catch (err) {
            console.log('postCollectionDocumentLink -> error: ', err)
        }        
    }


    const postCollectionDocumentUnlink = async (study_collection_id: string, documents_ids: [string]) => {

        console.log('deleteCollectionDocumentUnlink')
        //Fetch post with request.project_document
        try {
            let response = await fetch(`${base_url}/study_collection/${study_collection_id}/documents`, {
                method: 'delete',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ documents_ids })
            })
            
            console.log('deleteCollectionDocumentUnlink -> response: ', response)
            if (response.status == 202) {
                let projectDocumentUnlink = await response.json()
                console.log(`postCollectionDocumentUnlink accepted, Response: ${projectDocumentUnlink}`)
            }
        } catch (err) {
            console.log('deleteCollectionDocumentUnlink -> error: ', err)
        }
    }


    // Delete a study Collection
    const deleteStudyCollection = async (study_collection_id: string) => {

        console.log('deleteStudyCollection -> study_collection_id: ', study_collection_id)
        //Fetch post with request.study_collection
        try {
            let response = await fetch(`${base_url}/study_collection/${study_collection_id}`, {
                method: 'delete',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                }
            })
            
            console.log('deleteStudyCollection -> response: ', response)
            if (response.status == 202) {
                let studyCollection = await response.json()
                console.log(`deleteStudyCollection accepted, study project id ${study_collection_id} to deleted Study Collection`)
            }
        } catch (err) {
            console.log('deleteStudyCollection -> error: ', err)
        }
    }

    const searchCollections = async (user_id: string, search_term: any) => {
        console.log('searchCollections -> user_id: ', user_id)
        //Fetch post with request.user_id
        try {
            let response = await fetch(`${base_url}/study_collection/${user_id}/search`, {
                method: 'post',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(search_term)
            })
            
            console.log('searchCollections -> response: ', response)
            if (response.status == 202) {
                searchResult.value = await response.json();
                console.log(`searchCollections accepted, ${searchResult}`);
            }
        } catch (err) {
            console.log('searchCollections -> error: ', err)
        }
    }

    return {
        studyCollections, studyCollection, errorStudyCollection, isPendingStudyCollection, getStudyCollections, getStudyCollection,
        getRelatedEntities, postStudyCollection, postCollectionDocumentLink, postCollectionDocumentUnlink, deleteStudyCollection,
        candidateDocs, getCandidatesDocs, searchCollections, searchResult
    }

}
