import io
import logging
from typing import Any, Optional

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class DriveService(BaseGoogleService):
    """Google Drive API service for metagen"""

    @property
    def service_name(self) -> str:
        return "drive"

    @property
    def service_version(self) -> str:
        return "v3"

    async def search_files(self, user_id: str, query: str, max_results: int = 10) -> dict[str, Any]:
        """
        Search Google Drive files

        Args:
            user_id: User identifier for credentials
            query: Search query string (file name or content)
            max_results: Maximum number of results to return

        Returns:
            Dict with count and files array
        """
        try:
            logger.debug(
                f"Searching Drive files for user {user_id}: "
                f"query='{query}', max_results={max_results}"
            )

            # Build search query for Google Drive API
            drive_query = f"name contains '{query}' and trashed=false"

            def _search_request(service: Any) -> Any:
                return service.files().list(
                    q=drive_query,
                    pageSize=max_results,
                    fields="files(id,name,mimeType,modifiedTime,size,webViewLink,owners)",
                )

            result = await self._execute_request(_search_request, user_id)
            files = result.get("files", [])

            # Format files for response
            formatted_files = []
            for file in files:
                owners = file.get("owners", [])
                owner_name = owners[0].get("displayName", "") if owners else ""

                formatted_files.append(
                    {
                        "id": file.get("id", ""),
                        "name": file.get("name", ""),
                        "type": file.get("mimeType", ""),
                        "modified": file.get("modifiedTime", ""),
                        "size": file.get("size", "0"),
                        "link": file.get("webViewLink", ""),
                        "owner": owner_name,
                    }
                )

            return {"count": len(formatted_files), "files": formatted_files, "success": True}

        except Exception as e:
            logger.error(f"Error searching Drive files: {str(e)}", exc_info=True)
            return self._format_error_response(e, {"count": 0, "files": [], "success": False})

    async def get_file(self, user_id: str, file_id: str) -> dict[str, Any]:
        """
        Get detailed information about a specific file

        Args:
            user_id: User identifier for credentials
            file_id: Google Drive file ID

        Returns:
            Dict with file details
        """
        try:
            logger.debug(f"Getting Drive file {file_id} for user {user_id}")

            def _get_file_request(service: Any) -> Any:
                return service.files().get(
                    fileId=file_id,
                    fields="id,name,mimeType,modifiedTime,createdTime,size,webViewLink,owners,description",
                )

            file_data = await self._execute_request(_get_file_request, user_id)

            owners = file_data.get("owners", [])
            owner_name = owners[0].get("displayName", "") if owners else ""

            return {
                "id": file_data.get("id", ""),
                "name": file_data.get("name", ""),
                "type": file_data.get("mimeType", ""),
                "modified": file_data.get("modifiedTime", ""),
                "created": file_data.get("createdTime", ""),
                "size": file_data.get("size", "0"),
                "link": file_data.get("webViewLink", ""),
                "owner": owner_name,
                "description": file_data.get("description", ""),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error getting Drive file {file_id}: {str(e)}", exc_info=True)
            return self._format_error_response(e, {"id": file_id, "success": False})

    async def upload_file(
        self,
        user_id: str,
        file_path: str,
        name: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Upload a file to Google Drive

        Args:
            user_id: User identifier for credentials
            file_path: Local path to file to upload
            name: Optional name for the file (defaults to filename)
            parent_folder_id: Optional parent folder ID

        Returns:
            Dict with uploaded file details
        """
        try:
            import os

            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")

            logger.debug(f"Uploading file {file_path} to Drive for user {user_id}")

            file_name = name or os.path.basename(file_path)

            def _upload_request(service: Any) -> Any:
                file_metadata: dict[str, Any] = {"name": file_name}
                if parent_folder_id:
                    file_metadata["parents"] = [parent_folder_id]

                media = MediaFileUpload(file_path, resumable=True)
                return service.files().create(
                    body=file_metadata, media_body=media, fields="id,name,mimeType,size,webViewLink"
                )

            result = await self._execute_request(_upload_request, user_id)

            return {
                "id": result.get("id", ""),
                "name": result.get("name", ""),
                "type": result.get("mimeType", ""),
                "size": result.get("size", "0"),
                "link": result.get("webViewLink", ""),
                "success": True,
                "message": f"File '{file_name}' uploaded successfully",
            }

        except Exception as e:
            logger.error(f"Error uploading file {file_path}: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"id": None, "name": name or file_path, "success": False}
            )

    async def download_file(self, user_id: str, file_id: str, local_path: str) -> dict[str, Any]:
        """
        Download a file from Google Drive

        Args:
            user_id: User identifier for credentials
            file_id: Google Drive file ID
            local_path: Local path where file should be saved

        Returns:
            Dict with download status
        """
        try:
            logger.debug(f"Downloading Drive file {file_id} to {local_path} for user {user_id}")

            def _download_request(service: Any) -> Any:
                # First get file metadata
                file_metadata = service.files().get(fileId=file_id).execute()

                # Download file content
                request = service.files().get_media(fileId=file_id)
                file_io = io.BytesIO()
                downloader = MediaIoBaseDownload(file_io, request)

                done = False
                while done is False:
                    status, done = downloader.next_chunk()

                # Write to local file
                with open(local_path, "wb") as f:
                    f.write(file_io.getvalue())

                return file_metadata

            file_metadata = await self._execute_request(_download_request, user_id)

            return {
                "id": file_metadata.get("id", ""),
                "name": file_metadata.get("name", ""),
                "local_path": local_path,
                "size": file_metadata.get("size", "0"),
                "success": True,
                "message": f"File downloaded to {local_path}",
            }

        except Exception as e:
            logger.error(f"Error downloading file {file_id}: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"id": file_id, "local_path": local_path, "success": False}
            )

    async def share_file(
        self, user_id: str, file_id: str, email: str, role: str = "reader"
    ) -> dict[str, Any]:
        """
        Share a file with another user

        Args:
            user_id: User identifier for credentials
            file_id: Google Drive file ID
            email: Email address to share with
            role: Permission role ('reader', 'writer', 'owner')

        Returns:
            Dict with sharing status
        """
        try:
            logger.debug(f"Sharing Drive file {file_id} with {email} as {role} for user {user_id}")

            def _share_request(service: Any) -> Any:
                permission = {"type": "user", "role": role, "emailAddress": email}

                return service.permissions().create(
                    fileId=file_id,
                    body=permission,
                    sendNotificationEmail=True,
                    fields="id,role,emailAddress",
                )

            result = await self._execute_request(_share_request, user_id)

            return {
                "file_id": file_id,
                "permission_id": result.get("id", ""),
                "email": result.get("emailAddress", ""),
                "role": result.get("role", ""),
                "success": True,
                "message": f"File shared with {email} as {role}",
            }

        except Exception as e:
            logger.error(f"Error sharing file {file_id}: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"file_id": file_id, "email": email, "role": role, "success": False}
            )

    async def create_folder(
        self, user_id: str, name: str, parent_folder_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Create a new folder in Google Drive

        Args:
            user_id: User identifier for credentials
            name: Folder name
            parent_folder_id: Optional parent folder ID

        Returns:
            Dict with folder details
        """
        try:
            logger.debug(f"Creating Drive folder '{name}' for user {user_id}")

            def _create_folder_request(service: Any) -> Any:
                folder_metadata: dict[str, Any] = {
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                }
                if parent_folder_id:
                    folder_metadata["parents"] = [parent_folder_id]

                return service.files().create(body=folder_metadata, fields="id,name,webViewLink")

            result = await self._execute_request(_create_folder_request, user_id)

            return {
                "id": result.get("id", ""),
                "name": result.get("name", ""),
                "link": result.get("webViewLink", ""),
                "success": True,
                "message": f"Folder '{name}' created successfully",
            }

        except Exception as e:
            logger.error(f"Error creating folder '{name}': {str(e)}", exc_info=True)
            return self._format_error_response(e, {"name": name, "success": False})
