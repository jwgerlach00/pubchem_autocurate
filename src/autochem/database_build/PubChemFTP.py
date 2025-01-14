import os
import shutil
from ftplib import FTP
from tqdm import tqdm
import hashlib
import zipfile
import socket
import time


class PubChemFTP():
    def __init__(self, absolute_out_dir:str, overwrite:bool=False) -> None:
        self.__absolute_out_dir = absolute_out_dir
        self.__overwrite = overwrite
        
        # Path to send stuff that fails error checking
        self.__bad_file_path = os.path.join(self.__absolute_out_dir, 'bad_files')
        
        # Make directory and set directory names to be populated
        self._make_dir()
        self.__protein_target_ftp_directory = 'pubchem/Target/'
        self.__protein_target_filename = 'protein2xrefs.gz'
        self.__substance_sdf_ftp_directory = 'pubchem/Substance/CURRENT-Full/SDF/'
        self.__bioassay_json_ftp_directory = 'pubchem/Bioassay/JSON/'
        self.__bioassay_asn_metadata_ftp_directory = 'pubchem/Bioassay/'
        self.__bioassay_asn_metadata_filename = 'pcassay2.asn'
        
        # FTP connection details
        self.__ftp_host = 'ftp.ncbi.nlm.nih.gov'
        self.__ftp_user = 'anonymous'
        self.__ftp_password = ''
        
        # Connect to the FTP server
        self._connect(dir_name='')
    
    def _connect(self, dir_name:str) -> None:
        time1 = time.time()
        self.__ftp = FTP(self.__ftp_host)
        self.__ftp.login(self.__ftp_user, self.__ftp_password)
        self.__ftp.cwd('/' + dir_name) # preface w/ root ('/') to clear previous cwd operations
        print('time to connect: ', time.time() - time1) # probably not even useful
        
    def _ftp_read(self, local_file_path:str, server_file_path:str, base_dir_name:str,
                  max_failed_attempts:int=5, reconnect_delay_seconds:int=25) -> None:
        for i in range(max_failed_attempts):
            try:
                with open(local_file_path, 'wb') as file:
                    self.__ftp.retrbinary(f'RETR {server_file_path}', file.write)
                break
            except socket.error: # re-connect to FTP server
                print('SOCKET ERROR')
                if i == max_failed_attempts - 1:
                    raise Exception(f'Failed to reconnect to FTP server after {max_failed_attempts} attempts')
                else:
                    self._connect(base_dir_name) # this assumes the thread is paused to connect
                    time.sleep(reconnect_delay_seconds)
            except Exception as e:
                if hasattr(e, 'message'):
                    print(f'Error downloading {server_file_path}: {e.message}')
                elif hasattr(e, 'args') and e.args:
                    print(f'Error downloading {server_file_path}: {e.args[0]}')
                else:
                    print(f'Error downloading {server_file_path}: {str(e)}')
    
    def download_all(self, verbose:bool=True) -> None:
        """
        Downloads all relevent data from PubChem FTP server.

        :param verbose: Whether to print status info to console at each step, defaults to True
        :type verbose: bool, optional
        """
        
        # Download protein target data 'protein2xrefs.gz'
        if verbose:
            print('Downloading protein target data...')
        try:
            self.download_protein_target_data(verbose=verbose)
        except Exception as e:
            print(f'Error downloading protein target data: {e}')
        
        # Download substance SDFs
        if verbose:
            print('Downloading substance SDFs...')
        try:
            self.download_substance_sdfs(verbose=verbose)
        except Exception as e:
            print(f'Error downloading substance SDFs: {e}')
        
        # Download bioassay JSONs
        if verbose:
            print('Downloading bioassay JSONs...')
        try:
            self.download_bioassay_jsons(verbose=verbose)
        except Exception as e:
            print(f'Error downloading bioassay JSONs: {e}')
        
        if verbose:
            print('Downloading bioassay ASN metadata...')
        try:
            self.download_bioassay_asn_metadata(verbose=verbose)
        except Exception as e:
            print(f'Error downloading bioassay ASN metadata: {e}')
            
    def download_protein_target_data(self, verbose:bool=True) -> None:
        """
        Downloads protein2xref.gz which is used to link protein accessions to UniProt IDs.

        :param verbose: Whether to print status info to console, defaults to True
        :type verbose: bool, optional
        """
        
        # Make directory locally, change directory on server, get aboslute path to directory locally
        protein_target_out_dir = self._cwd_on_server_and_make_dir_locally(self.__protein_target_ftp_directory)
        
        # Path to the single file that needs to be downloaded
        file_path = os.path.join(protein_target_out_dir, self.__protein_target_filename)
        
        self._ftp_read(file_path, self.__protein_target_filename, self.__protein_target_ftp_directory)
        if verbose:
            print(f'Downloaded: {self.__protein_target_filename}')

    def download_substance_sdfs(self, max_bad_checksum_download_attempts:int=5, verbose:bool=True) -> None:
        """
        Downloads all substance files as SDFs (zipped using gzip) as structured in the PubChem FTP server. Uses md5
        checksum files provided by PubChem to verify download integrity.

        :param max_bad_checksum_download_attempts: The maxmimum number of attempts to download a file with a bad md5
            checksum, defaults to 5
        :type max_bad_checksum_download_attempts: int, optional
        :param verbose: Whether to print status info to console, defaults to True
        :type verbose: bool, optional
        """
        
        # Make directory locally, change directory on server, get aboslute path to directory locally
        substance_sdf_out_dir = self._cwd_on_server_and_make_dir_locally(self.__substance_sdf_ftp_directory)
        
        filenames = list(set([filename.split('.')[0] for filename in self.__ftp.nlst()])) # remove extensions and \
            # merge duplicates so that .sdf.gz and .sdf.gz.md5 are iterated at the same time

        # Download each file
        for filename in (tqdm(filenames) if verbose else filenames):
            file_path_no_extension = os.path.join(substance_sdf_out_dir, filename)
            
            try:
                if filename.startswith('README'): # README file, no checksum; Saved bc we still want to preserve these
                    self._ftp_read(file_path_no_extension, filename, self.__substance_sdf_ftp_directory) # README has no extension already
                    continue
            
                else: # not a README
                    # Try to download up to (max_bad_checksum_download_attempts) times if checksum fails
                    for i in range(max_bad_checksum_download_attempts):
                        # Open and write SDF file, should overwrite if already exists in case of bad checksum                            
                        self._ftp_read(f'{file_path_no_extension}.sdf.gz', f'{filename}.sdf.gz', self.__substance_sdf_ftp_directory)
                        # Open and write MD5 file, should overwrite if already exists in case of bad checksum
                        self._ftp_read(f'{file_path_no_extension}.sdf.gz.md5', f'{filename}.sdf.gz.md5', self.__substance_sdf_ftp_directory)
                            
                        # Check MD5
                        if self._substance_sdf_md5_checksum(filename.split('.')[0]): # just the name, no extension
                            break
                        elif i == max_bad_checksum_download_attempts - 1: # We've reached the max number of attempts \
                            # so skip this file
                            print(f'Could not download substance SDF: {filename} after \
                                {max_bad_checksum_download_attempts} attempts. Skipping...')

                            # Move bad files away
                            os.rename(f'{file_path_no_extension}.sdf.gz', os.path.join(self.__bad_file_path,
                                                                                    f'{filename}.sdf.gz'))
                            os.rename(f'{file_path_no_extension}.sdf.gz.md5', os.path.join(self.__bad_file_path,
                                                                                        f'{filename}.sdf.gz.md5'))
                        elif verbose:
                            print(f'Bad checksum for: {filename}. Trying again...')
                        

                        if i == max_bad_checksum_download_attempts - 1:
                            print(f'Could not download substance SDF: {filename} after \
                                {max_bad_checksum_download_attempts} attempts. Skipping...')
                    
                    if verbose:
                        print(f'Downloaded: {filename}')
            except Exception as e:
                print(f'Error downloading {filename}: {e}')
                
    def download_bioassay_jsons(self, max_bad_zip_file_attempts:int=5, verbose:bool=True) -> None:
        """
        Downloads all bioassays as JSON files (zipped using gzip) as structured in the PubChem FTP server.

        :param verbose: Whether to print status info to console, defaults to True
        :type verbose: bool, optional
        """
        
        # Make directory locally, change directory on server, get aboslute path to directory locally
        bioassay_json_out_dir = self._cwd_on_server_and_make_dir_locally(self.__bioassay_json_ftp_directory)

        # Retrieve a list of all file names in the directory
        filenames = self.__ftp.nlst()        

        # Download each file
        for filename in (tqdm(filenames[397:]) if verbose else filenames):
            file_path = os.path.join(bioassay_json_out_dir, filename)
            
            try:
                if filename.startswith('README'): # README file, no error checking; Saved bc we still want to preserve \
                    # these
                    self._ftp_read(file_path, filename, self.__bioassay_json_ftp_directory) # README has no extension already
                    continue
                
                # Try to download up to (max_bad_zip_file_attempts) times if error check fails
                for i in range(max_bad_zip_file_attempts):
                    self._ftp_read(file_path, filename, self.__bioassay_json_ftp_directory)
                    
                    # Try to open the zipped directory, if it can't open, re-download
                    if PubChemFTP._error_check_bioassay_json(file_path):
                        break
                    elif i == max_bad_zip_file_attempts - 1: # We've reached the max number of attempts so skip this \
                        # file
                        print(f'Could not download bioassay JSON: {filename} after {max_bad_zip_file_attempts} \
                            attempts. Skipping...')
                        
                        # Move the bad file away
                        os.rename(file_path, os.path.join(self.__bad_file_path, filename))
                    elif verbose:
                        print(f'Bad error check for: {filename}. Trying again...')

                if verbose:
                    print(f'Downloaded: {filename}')
            except Exception as e:
                if hasattr(e, 'message'):
                    print(f'Error downloading {filename}: {e.message}')
                elif hasattr(e, 'args') and e.args:
                    print(f'Error downloading {filename}: {e.args[0]}')
                else:
                    print(f'Error downloading {filename}: {str(e)}')
                
    def download_bioassay_asn_metadata(self, verbose:bool=True) -> None:
        """
        Downloads the ASN structure which defines certain integer-encodings in the bioassay data. This is not currently 
        used within the PubChemDB module because the data structure is currently presumed unreadable. These values have
        been hard-coded into the PubChemDB module in.

        :param verbose: Whether to print status to console, defaults to True
        :type verbose: bool, optional
        """
        
        # Make directory locally, change directory on server, get aboslute path to directory locally
        bioassay_asn_metadata_out_dir = self._cwd_on_server_and_make_dir_locally(
            self.__bioassay_asn_metadata_ftp_directory)
        
        # Path to the single file that needs to be downloaded
        file_path = os.path.join(bioassay_asn_metadata_out_dir, self.__bioassay_asn_metadata_filename)
        
        self._ftp_read(file_path, self.__bioassay_asn_metadata_filename, self.__bioassay_asn_metadata_ftp_directory)
        if verbose:
            print(f'Downloaded: {self.__bioassay_asn_metadata_filename}')
                
    def _make_dir(self) -> None:
        """
        Conditionally create a directory for the output files based on whether the directory exists and whether it is 
        overwritable.

        :raises ValueError: Overwrite is False but directory is not empty
        """
        if not os.path.exists(self.__absolute_out_dir): # create directory if it doesn't exist
            os.makedirs(self.__absolute_out_dir)
        elif len(os.listdir(self.__absolute_out_dir)) > 0 and self.__overwrite == False: # raise error if directory \
            # exists and overwrite is False
            raise ValueError(f'Directory {self.__absolute_out_dir} is not empty. Set overwrite=True to overwrite \
                files. Note that this will delete all files in {self.__absolute_out_dir}.')
        else: # delete directory and recreate if overwrite is True
            shutil.rmtree(self.__absolute_out_dir)
            os.makedirs(self.__absolute_out_dir)
            
        os.makedirs(self.__bad_file_path)
            
    def _cwd_on_server_and_make_dir_locally(self, dir_name:str) -> str:
        """
        Changes the current working directory on the FTP server to the specified directory and creates a directory
        locally with the same hierarchical structure. Returns the absolute path to the directory locally.

        :param dir_name: Name of directory
        :type dir_name: str
        :return: Absolute path to the directory locally
        :rtype: str
        """
        # Change to the directory on the FTP server
        self.__ftp.cwd('/' + dir_name) # preface w/ root ('/') to clear previous cwd operations
        
        # Make the directory locally
        out_dir = os.path.join(self.__absolute_out_dir, dir_name)
        os.makedirs(out_dir)
        
        return out_dir
            
    def _substance_sdf_md5_checksum(self, filename_no_extension:str) -> bool:
        """
        Checks the MD5 checksum of a Substance SDF file against the MD5 checksum. Assumes that the MD5 checksum file is
        in the same directory as the SDF file and has the same name as the SDF file, but with a '.md5' extension.

        :param filename_no_extension: Name of file, not path, before ('.')
        :type filename_no_extension: str
        :return: Status of whether or not the MD5 checksums match
        :rtype: bool
        """
        file_stem = os.path.join(self.__absolute_out_dir, self.__substance_sdf_ftp_directory, filename_no_extension)
        calc_md5 = self._calculate_md5(f'{file_stem}.sdf.gz')
        read_md5 = open(f'{file_stem}.sdf.gz.md5', 'r').read().split()[0]
        return calc_md5 == read_md5
    
    @staticmethod
    def _calculate_md5(filepath:str) -> str:
        """
        Calculates the Message Digest Algorithm 5 crytographic hash of a file.

        :param filepath: Path to file to be hashed
        :type filepath: str
        :return: MD5 hash of file
        :rtype: str
        """
        md5_hash = hashlib.md5()
        with open(filepath, 'rb') as file:
            for chunk in iter(lambda: file.read(4096), b''):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    
    @staticmethod
    def _error_check_bioassay_json(absolute_file_path:str) -> bool:
        try:
            zipfile.ZipFile(absolute_file_path, 'r')
            return True
        except Exception:
            return False
        

if __name__ == '__main__':
    pc_ftp = PubChemFTP(os.path.join(os.getcwd(), 'pubchem_ftp_data'), overwrite=True)
    
    # Download protein target xref, substance sdf, and bioassay json files
    pc_ftp.download_all(verbose=True)
