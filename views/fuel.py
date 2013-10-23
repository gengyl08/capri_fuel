from django import forms
from django.shortcuts import render_to_response
from django.core.urlresolvers import reverse as urllookup
from django.template import RequestContext
from django.http import HttpResponseRedirect, HttpResponseNotFound, HttpResponsePermanentRedirect, HttpResponse
from django.views.decorators.csrf import csrf_protect
from besite.views.auth import requires_liveuser, requires_user
from besite.views.utils_forms import SequentialForm

from proto.besite import consts

from besite.views.account import FormExecuted

from stanford.bundles.upload import IMAGE_CODEX, SQS_REGION_NAME, SQS_BUCKET_NAME, SQS_PATH
from stanford.bundles.upload import upload as uploadImage

import logging

S3_URL = 'https://s3-{}.amazonaws.com/{}/{}'.format(SQS_REGION_NAME, SQS_BUCKET_NAME, SQS_PATH)

@requires_liveuser
def image(request, user, fuel_id, thumbnail=False):

    # check to make sure user owns the fuel-up
    fuel_id = int(fuel_id)
    f = user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_GET, id=fuel_id)
    if f is None:
        return HttpResponseNotFound()

    url = '{}{}{}_{}.jpg'.format(
            S3_URL,
            't/' if thumbnail else 'o/',
            IMAGE_CODEX.encode(user.user_id),
            fuel_id
            )
    return HttpResponsePermanentRedirect(url)

# this view function implements the "splash" page after the user logs in. The template here will implement the form inputs?
# custom decorator for requiring an account
def requires_liveuser_retain_path():
    def decorator(view):
        return requires_user(view, check_live=True, account_types=None, retain_path=True)
    return decorator

@requires_liveuser_retain_path()
def main(request, user):
    return render_to_response(
            'fuel/index.html',
            {'user': user, 'consts':consts},
            context_instance = RequestContext(request)
            )

@requires_liveuser
def indextemp(request, user):
    logging.getLogger('fe').debug('hi');
    return render_to_response(
            'fuel/index_temp.html',
            {'user': user, 'consts':consts},
            context_instance = RequestContext(request)
            )

@csrf_protect
@requires_liveuser
def fuelup_post(request, user):
    logging.getLogger('fe').debug('post');
    if request.method == 'POST':
        try:
            form = FuelupForm.submit(request, user)
        except FormExecuted as k:
            return HttpResponse("success")
    # if we got to this point: either the method was GET, or something wrong happened and the form was returned. 
    return HttpResponse("error")


# this view function implements the first step -- upload of image, typing in of information, and submission
@csrf_protect
@requires_liveuser
def step1(request, user):

    #return HttpResponse(request.POST['type']+request.FILES['image'])
    # if there is a form to process, do it

    if request.method == 'POST': 
        # trigger form processing here
        # sorry, this is a backwards design pattern in existing code. We're raising an exception to indicate that processing succeeded *(WHAT)*. Just try to flow with this...
        try:
            form = Step1Form.submit(request, user)

        # form was successfully processed
        except FormExecuted:
            
            d = {'user': user, 'consts': consts}
            d.update(k.data)
            # go onto the next step
            return render_to_response(
                    'fuel/secondstep.html',
                    d,
                    context_instance = RequestContext(request)
                    )
    
    # if we got to this point: either the method was GET, or something wrong happened and the form was returned. 
    return render_to_response(
            'fuel/index.html',
            {'user': user, 'consts':consts, 'form':Step1Form()},
            context_instance = RequestContext(request)
            )

class FuelupForm(SequentialForm):
    # define your fields here
    receipt = forms.ImageField(required=True)
    price = forms.FloatField(required=True,min_value=0,max_value=10.0)
    gallons = forms.FloatField(required=True,min_value=0,max_value=30.0)
    grade = forms.IntegerField(required=True)
    chain = forms.CharField(required=True)

    @staticmethod
    def submit(request, user):
        # process your form here
        form = FuelupForm(request.POST, request.FILES)
        if not form.is_valid():
            logging.getLogger('fe').debug('not valid')
            form.markErroneous('Invalid data submitted')
            return form
        else:
            # process form, call API to update, etc
            fuel_id = user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_CREATE)
            amount = float(form.cleaned_data['gallons'])
            price = float(form.cleaned_data['price'])
            grade = int(form.cleaned_data['grade'])
            chain = str(form.cleaned_data['chain'])
            #logging.getLogger('fe').debug('%g %g', amount, price)
            user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_UPDATE, id=fuel_id,
                    fueldata={'amount': amount, 'price': price})
            # apparently you can't pass an image through protobuf! so we're calling it directly from the front end
            uploadImage(user, fuel_id, form.cleaned_data['receipt'])
            
            k = FormExecuted()
            
            k.data = {
                    'fuel_id': fuel_id,
                    'amount': amount,
                    'price': price,
                    'grade': grade,
                    'chain': chain,
                    'receipt': '/fuel/image/{id:d}/'.format(id=fuel_id),
                    }
            raise k

# this form handles the typing in of information and uploading of image
class Step1Form(SequentialForm):
    # define your fields here
    image = forms.ImageField(required=True)
    price = forms.FloatField(required=True,min_value=0,max_value=10.0)
    gallons = forms.FloatField(required=True,min_value=0,max_value=30.0)
#    type = forms.CharField(required=True)

    @staticmethod
    def submit(request, user):
        # process your form here
        form = Step1Form(request.POST, request.FILES)
        if not form.is_valid():
            logging.getLogger('fe').debug('not valid')
            form.markErroneous('Invalid data submitted')
            return form
        else:
            # process form, call API to update, etc
            fuel_id = user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_CREATE)
            amount = float(form.cleaned_data['gallons'])
            price = float(form.cleaned_data['price'])
            logging.getLogger('fe').debug('%g %g', amount, price)
            user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_UPDATE, id=fuel_id, fueldata={'amount': amount, 'price': price})
#            user.bundle(consts.CAPRI_FUEL).doAction(consts.CAPRI_FUEL_UPLOAD_IMAGE, id=fuel_id, image=form.cleaned_data['image'])
            # apparently you can't pass an image through protobuf! so we're calling it directly from the front end
            uploadImage(user, fuel_id, form.cleaned_data['image'])
            k = FormExecuted()
            k.data = {
                    'fuel_id': fuel_id,
                    'amount': amount,
                    'price': price,
                    'image': '/fuel/image/{id:d}/'.format(id=fuel_id),
                    }
            raise k

@csrf_protect
@requires_liveuser
def play(request, user):
    return render_to_response(
            'fuel/play.html',
            {'user': user, 'consts':consts},
            context_instance = RequestContext(request)
            )

@csrf_protect
@requires_liveuser
def finalprize(request, user):
    return render_to_response(
            'fuel/finalprize.html',
            {'user': user, 'consts':consts},
            context_instance = RequestContext(request)
            )
