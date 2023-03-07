"""
`tiktok_uploader` module for uploading videos to TikTok

Key Functions
-------------
upload_video : Uploads a single TikTok video
upload_videos : Uploads multiple TikTok videos
"""
from os.path import abspath, exists
import time

from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from tiktok_uploader.browsers import get_browser
from tiktok_uploader.auth import AuthBackend
from tiktok_uploader import config


def upload_video(*args, filename=None, description='', username='',
                 password='', cookies='', **kwargs):
    """
    Uploads a single TikTok video.

    Conder using `upload_videos` if using multiple videos

    Parameters
    ----------
    filename : str
        The path to the video to upload
    description : str
        The description to set for the video
    cookies : str
        The cookies to use for uploading
    """
    auth = AuthBackend(username=username, password=password, cookies=cookies)

    return upload_videos(
            videos=[ { 'path': filename, 'description': description } ],
            auth=auth,
            *args, **kwargs
        )


def upload_videos(videos: list = None, auth: AuthBackend = None, browser='chrome',
                  browser_agent=None, on_complete=None, headless=False, num_retires : int = 1, *args, **kwargs):
    """
    Uploads multiple videos to TikTok

    Parameters
    ----------
    videos : list
        A list of dictionaries containing the video's ('path') and description ('description')
    browser : str
        The browser to use for uploading
    browser_agent : selenium.webdriver
        A selenium webdriver object to use for uploading
    on_complete : function
        A function to call when the upload is complete
    headless : bool
        Whether or not the browser should be run in headless mode
    num_retries : int
        The number of retries to attempt if the upload fails
    *args :
        Additional arguments to pass into the upload function
    **kwargs :
        Additional keyword arguments to pass into the upload function

    Returns
    -------
    failed : list
        A list of videos which failed to upload
    """
    if not videos:
        print("No videos were provided")
        return

    if not browser_agent: # user-specified browser agent
        driver = get_browser(name=browser, headless=headless, *args, **kwargs)
    else:
        driver = browser_agent

    driver = auth.authenticate_agent(driver)

    failed = []
    # uploads each video
    for video in videos:
        print(f'Uploading {video.get("path")}')
        try:
            path = abspath(video.get('path'))
            description = video.get('description', '')
        except Exception as _:
            print(f'Invalid video: {video}')
            failed.append(video)
            continue

        # Video must be of supported type
        if not _check_valid_path(path):
            print(f'{path} is invalid, skipping')
            failed.append(video)
            continue

        try:
            complete_upload_form(driver, path, description, num_retires = num_retires, *args, **kwargs)
        except Exception as exception:
            print(exception)
            failed.append(video)

        if on_complete: # calls the user-specified on-complete function
            on_complete(video)

    if config['quit_on_end']:
        driver.quit()

    return failed


def complete_upload_form(driver, path: str, description: str, *args, **kwargs) -> None:
    """
    Actually uploades each video

    Parameters
    ----------
    driver : selenium.webdriver
        The selenium webdriver to use for uploading
    path : str
        The path to the video to upload
    """
    _go_to_upload(driver, *args, **kwargs)
    _set_video(driver, path)
    _set_interactivity(driver, *args, **kwargs)
    _set_description(driver, description)
    _post_video(driver)


def _go_to_upload(driver) -> None:
    """
    Navigates to the upload page, switches to the iframe and waits for it to load

    Parameters
    ----------
    driver : selenium.webdriver
    """
    driver.get(config['paths']['upload'])

    # changes to the iframe
    iframe_selector = EC.presence_of_element_located(
        (By.XPATH, config['selectors']['upload']['iframe'])
        )
    iframe = WebDriverWait(driver, config['explicit_wait']).until(iframe_selector)
    driver.switch_to.frame(iframe)

    # waits for the iframe to load
    root_selector = EC.presence_of_element_located((By.ID, 'root'))
    WebDriverWait(driver, config['explicit_wait']).until(root_selector)


def _set_description(driver, description: str) -> None:
    """
    Sets the description of the video

    Parameters
    ----------
    driver : selenium.webdriver
    description : str
        The description to set
    """
    if description is None:
        # if no description is provided, filename
        return

    saved_description = description # save the description in case it fails

    desc = driver.find_element(By.XPATH, config['selectors']['upload']['description'])
    print(desc.get_attribute('value'))

    # desc populates with filename before clearing
    WebDriverWait(driver, 10).until(lambda driver: desc.get_attribute('value') != '')
    print(desc.get_attribute('value'))

    _clear(desc)
    print(desc.get_attribute('value'))

    try:
        if len(description) > config['max_description_length']:
            raise DescriptionTooLong()

        while description:
            nearest_mention = description.find('@')
            nearest_hash = description.find('#')

            if nearest_mention == 0 or nearest_hash == 0:
                desc.send_keys('@' if nearest_mention == 0 else '#')

                # wait for the frames to load
                time.sleep(config['implicit_wait'])

                name = description[1:].split(' ')[0]
                desc.send_keys(name)

                if nearest_mention == 0: # @ case
                    mention_xpath = config['selectors']['upload']['mentions'].format(name)
                    condition = EC.presence_of_element_located((By.XPATH, mention_xpath))
                else:
                    hashtag_xpath = config['selectors']['upload']['hashtags'].format(name)
                    condition = EC.presence_of_element_located((By.XPATH, hashtag_xpath))

                elem = WebDriverWait(driver, config['explicit_wait']).until(condition)

                elem.click()
                description = description[len(name) + 1:]
            else:
                min_index = min(nearest_mention, nearest_hash)
                desc.send_keys(description[:min_index])
                description = description[min_index:]
    except Exception as exception:
        print(exception)
        desc.clear()
        desc.send_keys(saved_description) # if fail, use saved description


def _clear(element) -> None:
    """
    Clears the text of the element (an issue with the TikTok website when automating)

    Parameters
    ----------
    element
        The text box to clear
    """
    element.clear()
    element.send_keys(Keys.CONTROL + 'a')
    element.send_keys(Keys.DELETE)


def _set_video(driver, *args, path: str = '', num_retries: int = 1, **kwargs) -> None:
    """
    Sets the video to upload

    Parameters
    ----------
    driver : selenium.webdriver
    path : str
        The path to the video to upload
    num_retries : number of retries (can occassionally fail)
    """
    # uploades the element
    for _ in range(num_retries):
        try:
            upload_box = driver.find_element(By.XPATH, config['selectors']['upload']['upload_video'])
            upload_box.send_keys(path)

            # waits for the upload progress bar to disappear
            upload_progress = EC.presence_of_element_located(
                (By.XPATH, config['selectors']['upload']['upload_progress'])
                )

            WebDriverWait(driver, config['explicit_wait']).until_not(upload_progress)

            # waits for the video to upload
            upload_confirmation = EC.presence_of_element_located(
                (By.XPATH, config['selectors']['upload']['upload_confirmation'])
                )

            # NOTE (IMPORTANT): implicit wait as video should already be uploaded if not failed
            # An exception throw here means the video failed to upload an a retry is needed
            WebDriverWait(driver, config['implicit_wait']).until(upload_confirmation)

            # wait until a non-draggable image is found
            process_confirmation = EC.presence_of_element_located(
                (By.XPATH, config['selectors']['upload']['process_confirmation'])
                )
            WebDriverWait(driver, config['explicit_wait']).until(process_confirmation)
            return
        except Exception as exception:
            print(exception)


def _post_video(driver) -> None:
    """
    Posts the video

    Parameters
    ----------
    driver : selenium.webdriver
    """
    post = driver.find_element(By.XPATH, config['selectors']['upload']['post'])
    post.click()

    # waits for the video to upload
    post_confirmation = EC.presence_of_element_located(
        (By.XPATH, config['selectors']['upload']['post_confirmation'])
        )
    WebDriverWait(driver, config['explicit_wait']).until(post_confirmation)


def _set_interactivity(driver, comment=True, stitch=True, duet=True, *args, **kwargs) -> None:
    """
    Sets the interactivity settings of the video

    Parameters
    ----------
    driver : selenium.webdriver
    comment : bool
        Whether or not to allow comments
    stitch : bool
        Whether or not to allow stitching
    duet : bool
        Whether or not to allow duets
    """

    comment_box = driver.find_element(By.XPATH, config['selectors']['upload']['comment'])
    stitch_box = driver.find_element(By.XPATH, config['selectors']['upload']['stitch'])
    duet_box = driver.find_element(By.XPATH, config['selectors']['upload']['duet'])

    # xor the current state with the desired state
    if comment ^ comment_box.is_selected():
        comment_box.click()

    if stitch ^ stitch_box.is_selected():
        stitch_box.click()

    if duet ^ duet_box.is_selected():
        duet_box.click()

def _check_valid_path(path: str) -> bool:
    """
    Returns whether or not the filetype is supported by TikTok
    """
    return exists(path) and path.split('.')[-1] in config['supported_file_types']


class DescriptionTooLong(Exception):
    """
    A video description longer than the maximum allowed by TikTok's website (not app) uploader
    """
